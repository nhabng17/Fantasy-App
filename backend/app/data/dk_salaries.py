"""Fetch DraftKings salary data from their public draftgroups API."""

import logging
import unicodedata
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.config import SCRAPE_HEADERS
from app.database import async_session
from app.models import Player

logger = logging.getLogger(__name__)

DK_CONTESTS_URL = "https://www.draftkings.com/lobby/getcontests?sport=NBA"
DK_DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{group_id}/draftables"

CLASSIC_GAME_TYPE = 70

_NAME_SUFFIXES = {"jr.", "jr", "sr.", "sr", "ii", "iii", "iv", "v"}

# DK occasionally uses different team abbreviations than nba_api
DK_TEAM_MAP = {
    "SA": "SAS",
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "PHO": "PHX",
    "WSH": "WAS",
    "CHA": "CHA",
}


def _normalize_name(name: str) -> str:
    """Transliterate diacritics to ASCII and strip suffixes for cross-source matching."""
    ascii_name = "".join(
        c for c in unicodedata.normalize("NFKD", name)
        if unicodedata.category(c) != "Mn"
    )
    parts = [p for p in ascii_name.lower().split() if p.rstrip(".") not in _NAME_SUFFIXES]
    return " ".join(parts)


async def fetch_and_store_dk_salaries() -> int:
    """Fetch today's DraftKings salaries from all slates and update player records.

    Returns the number of players matched and updated.
    """
    try:
        group_ids = await _find_todays_slates()
        if not group_ids:
            logger.warning("No DraftKings slates found for today")
            return 0

        salary_map: dict[tuple, dict] = {}
        for gid in group_ids:
            slate_map = await _fetch_draftables(gid)
            for key, val in slate_map.items():
                if key not in salary_map:
                    salary_map[key] = val

        unmatched_teams = await _get_unmatched_teams(salary_map)
        if unmatched_teams:
            extra = await _probe_nearby_slates(group_ids, unmatched_teams)
            for key, val in extra.items():
                if key not in salary_map:
                    salary_map[key] = val

        if not salary_map:
            logger.warning("No draftable players found across any slate")
            return 0

        matched = await _update_player_salaries(salary_map)
        logger.info(
            f"DK salaries: {len(salary_map)} draftables from "
            f"{len(group_ids)}+ slates, {matched} matched to DB"
        )
        return matched
    except Exception as e:
        logger.error(f"Failed to fetch DK salaries: {e}")
        return 0


async def _find_todays_slates() -> list[int]:
    """Find all classic slates covering today's and tonight's games.

    DK uses EST dates, which can differ from local time. We check both
    today and tomorrow to ensure we catch evening slates that DK lists
    under the next calendar day.
    """
    async with httpx.AsyncClient(headers=SCRAPE_HEADERS, timeout=15) as client:
        resp = await client.get(DK_CONTESTS_URL)
        resp.raise_for_status()

    data = resp.json()
    groups = data.get("DraftGroups", [])

    now = datetime.now()
    valid_dates = {
        now.strftime("%Y-%m-%d"),
        (now + timedelta(days=1)).strftime("%Y-%m-%d"),
    }

    today_groups = []
    for g in groups:
        if g.get("GameTypeId") != CLASSIC_GAME_TYPE:
            continue
        if g.get("GameCount", 0) == 0:
            continue
        start = g.get("StartDateEst", "")
        start_date = start[:10] if start else ""
        if start_date in valid_dates:
            today_groups.append(g)

    if not today_groups:
        today_groups = [
            g for g in groups
            if g.get("GameTypeId") == CLASSIC_GAME_TYPE and g.get("GameCount", 0) > 0
        ]

    today_groups.sort(key=lambda g: g.get("GameCount", 0), reverse=True)
    group_ids = [g["DraftGroupId"] for g in today_groups]

    logger.info(
        f"Found {len(group_ids)} DK classic slates: "
        + ", ".join(f"{g['DraftGroupId']} ({g.get('GameCount')}g)" for g in today_groups)
    )
    return group_ids


async def _fetch_draftables(group_id: int) -> dict[str, dict]:
    """Fetch draftable players and return deduplicated salary map.

    Returns: {(normalized_name, team): {salary, dk_position, display_name}}
    """
    url = DK_DRAFTABLES_URL.format(group_id=group_id)
    async with httpx.AsyncClient(headers=SCRAPE_HEADERS, timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    data = resp.json()
    draftables = data.get("draftables", [])

    salary_map = {}
    for d in draftables:
        name = d.get("displayName", "").strip()
        team = d.get("teamAbbreviation", "").strip()
        salary = d.get("salary", 0)

        if not name or not salary:
            continue

        team = DK_TEAM_MAP.get(team, team)
        norm_name = _normalize_name(name)
        key = (norm_name, team)

        if key not in salary_map:
            salary_map[key] = {
                "salary": salary,
                "dk_position": d.get("position", ""),
                "display_name": name,
            }

    return salary_map


async def _get_unmatched_teams(salary_map: dict) -> set[str]:
    """Find teams in our DB that have no salary data yet."""
    covered_teams = {team for (_, team) in salary_map.keys()}
    async with async_session() as session:
        result = await session.execute(
            select(Player.team).distinct().where(Player.team != "FA")
        )
        db_teams = {r[0] for r in result}
    missing = db_teams - covered_teams
    if missing:
        logger.info(f"Teams missing DK salary data: {sorted(missing)}")
    return missing


async def _probe_nearby_slates(
    known_ids: list[int], target_teams: set[str],
) -> dict[tuple, dict]:
    """Probe DK group IDs near the known ones to find delisted slates.

    DK removes slates from the lobby after lock but the draftables
    endpoint still serves data for a while. Classic slates for the
    same day cluster within ~30 IDs of each other.
    """
    if not known_ids:
        return {}

    hi = max(known_ids)
    already = set(known_ids)
    remaining = set(target_teams)
    extra_map: dict[tuple, dict] = {}
    misses = 0

    async with httpx.AsyncClient(headers=SCRAPE_HEADERS, timeout=10) as client:
        for gid in range(hi - 1, max(hi - 50, 0), -1):
            if not remaining:
                break
            if gid in already:
                continue
            try:
                resp = await client.get(DK_DRAFTABLES_URL.format(group_id=gid))
                if resp.status_code != 200:
                    misses += 1
                    if misses > 10:
                        break
                    continue
                draftables = resp.json().get("draftables", [])
                if not draftables:
                    continue
                misses = 0

                slate_teams = {
                    DK_TEAM_MAP.get(d.get("teamAbbreviation", ""), d.get("teamAbbreviation", ""))
                    for d in draftables
                }
                if not (slate_teams & remaining):
                    continue

                logger.info(f"Found delisted DK slate {gid} with teams {sorted(slate_teams & remaining)}")
                for d in draftables:
                    name = d.get("displayName", "").strip()
                    team = DK_TEAM_MAP.get(
                        d.get("teamAbbreviation", "").strip(),
                        d.get("teamAbbreviation", "").strip(),
                    )
                    salary = d.get("salary", 0)
                    if not name or not salary:
                        continue
                    key = (_normalize_name(name), team)
                    if key not in extra_map:
                        extra_map[key] = {
                            "salary": salary,
                            "dk_position": d.get("position", ""),
                            "display_name": name,
                        }
                remaining -= slate_teams
            except Exception:
                continue

    return extra_map


async def _update_player_salaries(salary_map: dict) -> int:
    """Match DK salary data to players in DB and update salary field."""
    matched = 0

    async with async_session() as session:
        players = await session.execute(select(Player))
        all_players = players.scalars().all()

        for player in all_players:
            norm_name = _normalize_name(player.name)
            key = (norm_name, player.team)

            dk_data = salary_map.get(key)
            if dk_data:
                player.salary = dk_data["salary"]
                matched += 1

        await session.commit()

    return matched
