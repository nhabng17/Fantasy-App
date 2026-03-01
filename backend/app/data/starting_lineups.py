"""Scrape confirmed starting lineups from Rotowire.

The page at rotowire.com/basketball/nba-lineups.php renders lineup cards
server-side. Each game card (div.lineup.is-nba) contains two lineup__list
elements (one per team), each with players listed by position (PG, SG, SF, PF, C).
A div.lineup__status.is-confirmed indicates the lineup is confirmed.
"""

import logging
import unicodedata
from datetime import datetime, date

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, delete, and_, func
from sqlalchemy.dialects.sqlite import insert

from app.config import SCRAPE_HEADERS
from app.database import async_session
from app.models import StartingLineup, InjuryReport, Player, GameLog

logger = logging.getLogger(__name__)

ROTOWIRE_LINEUPS_URL = "https://www.rotowire.com/basketball/nba-lineups.php"


async def fetch_and_store_lineups() -> list[dict]:
    """Scrape Rotowire starting lineups and store in database."""
    try:
        lineups = await _scrape_rotowire_lineups()
        if not lineups:
            logger.warning("No lineups scraped from Rotowire")
            return []

        lineups = await _validate_lineups(lineups)

        today = date.today()

        async with async_session() as session:
            await session.execute(
                delete(StartingLineup).where(StartingLineup.game_date == today)
            )

            for lineup in lineups:
                stmt = insert(StartingLineup).values(
                    team=lineup["team"],
                    game_date=today,
                    opponent=lineup["opponent"],
                    pg=lineup.get("PG", ""),
                    sg=lineup.get("SG", ""),
                    sf=lineup.get("SF", ""),
                    pf=lineup.get("PF", ""),
                    c=lineup.get("C", ""),
                    confirmed=lineup["confirmed"],
                    last_updated=datetime.utcnow(),
                ).on_conflict_do_update(
                    index_elements=["team", "game_date"],
                    set_={
                        "opponent": lineup["opponent"],
                        "pg": lineup.get("PG", ""),
                        "sg": lineup.get("SG", ""),
                        "sf": lineup.get("SF", ""),
                        "pf": lineup.get("PF", ""),
                        "c": lineup.get("C", ""),
                        "confirmed": lineup["confirmed"],
                        "last_updated": datetime.utcnow(),
                    },
                )
                await session.execute(stmt)

            await session.commit()
        logger.info(f"Stored {len(lineups)} starting lineups")
        return lineups
    except Exception as e:
        logger.error(f"Failed to fetch starting lineups: {e}")
        return []


async def _scrape_rotowire_lineups() -> list[dict]:
    """Parse Rotowire's NBA starting lineups page.

    Structure per game card (div.lineup.is-nba):
      - div.lineup__abbr x2 (team abbreviations, e.g. "POR", "CHA")
      - div.lineup__list x2 (one per team)
        - First li has div.lineup__status (optional: .is-confirmed)
        - Remaining li's have span.lineup__pos (PG/SG/SF/PF/C) + a (player name)
    """
    async with httpx.AsyncClient(headers=SCRAPE_HEADERS, timeout=30) as client:
        resp = await client.get(ROTOWIRE_LINEUPS_URL)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    lineups = []

    game_cards = soup.select("div.lineup.is-nba")
    logger.info(f"Found {len(game_cards)} game cards on Rotowire")

    for card in game_cards:
        abbrs = card.select(".lineup__abbr")
        if len(abbrs) < 2:
            continue

        team_away = abbrs[0].get_text(strip=True).upper()
        team_home = abbrs[1].get_text(strip=True).upper()

        player_lists = card.select(".lineup__list")
        if len(player_lists) < 2:
            continue

        for idx, plist in enumerate(player_lists[:2]):
            team = team_away if idx == 0 else team_home
            opponent = team_home if idx == 0 else team_away

            confirmed = bool(plist.select_one(".lineup__status.is-confirmed"))

            players = plist.select("li")
            lineup = {
                "team": team,
                "opponent": opponent,
                "confirmed": confirmed,
            }

            for li in players:
                pos_el = li.select_one(".lineup__pos")
                name_el = li.select_one("a")

                if not pos_el or not name_el:
                    continue

                pos = pos_el.get_text(strip=True).upper()
                name = name_el.get_text(strip=True)

                if pos in ("PG", "SG", "SF", "PF", "C") and name:
                    lineup[pos] = name

            if any(lineup.get(p) for p in ("PG", "SG", "SF", "PF", "C")):
                lineups.append(lineup)

    return lineups


_NAME_SUFFIXES = {"jr.", "jr", "sr.", "sr", "ii", "iii", "iv", "v"}
_POSITIONS = ("PG", "SG", "SF", "PF", "C")

ADJACENT_POSITIONS: dict[str, list[str]] = {
    "PG": ["SG"],
    "SG": ["PG", "SF"],
    "SF": ["SG", "PF"],
    "PF": ["SF", "C"],
    "C": ["PF"],
}


def _normalize_name(name: str) -> str:
    """Transliterate diacritics to ASCII and strip suffixes for matching."""
    ascii_name = "".join(
        c for c in unicodedata.normalize("NFKD", name)
        if unicodedata.category(c) != "Mn"
    )
    parts = [p for p in ascii_name.lower().split() if p not in _NAME_SUFFIXES]
    return " ".join(parts)


def _name_variants(name: str) -> set[str]:
    """Generate all matchable forms of a player name.

    Handles full names, abbreviated first names, suffix stripping, and
    diacritics so that "M. Plumlee" matches "Mason Plumlee" and vice versa.
    """
    variants = set()
    lower = name.lower().strip()
    variants.add(lower)
    variants.add(_normalize_name(name))

    parts = name.strip().split()
    if len(parts) >= 2:
        first = parts[0].rstrip(".")
        rest_parts = [p for p in parts[1:] if p.lower().rstrip(".") not in _NAME_SUFFIXES]
        rest = " ".join(rest_parts).lower()

        if len(first) > 1:
            variants.add(f"{first[0].lower()}. {rest}")
        if len(first) == 1:
            variants.add(f"{first.lower()}. {rest}")

    return variants


def _build_injury_lookup(
    injuries: list[InjuryReport],
) -> dict[tuple[str, str], InjuryReport]:
    """Build a lookup keyed on every name variant + team."""
    lookup: dict[tuple[str, str], InjuryReport] = {}
    for inj in injuries:
        for variant in _name_variants(inj.player_name):
            lookup.setdefault((variant, inj.team), inj)
    return lookup


def _lookup_injury(
    injury_lookup: dict[tuple[str, str], InjuryReport],
    player_name: str,
    team: str,
) -> InjuryReport | None:
    """Find an injury report by trying every name variant against the lookup."""
    for variant in _name_variants(player_name):
        inj = injury_lookup.get((variant, team))
        if inj:
            return inj
    return None


async def _validate_lineups(lineups: list[dict]) -> list[dict]:
    """Cross-reference lineups with injury reports and usual starters.

    1. Remove Out/Doubtful players from lineup slots.
    2. For unconfirmed lineups, replace non-usual starters with the healthy
       usual starter when available (catches stale Rotowire data).
    """
    async with async_session() as session:
        injuries_result = await session.execute(select(InjuryReport))
        injury_lookup = _build_injury_lookup(injuries_result.scalars().all())

        for lineup in lineups:
            team = lineup["team"]

            for pos in _POSITIONS:
                player_name = lineup.get(pos, "")
                if not player_name:
                    continue

                inj = _lookup_injury(injury_lookup, player_name, team)

                if inj and inj.status in ("Out", "Doubtful"):
                    logger.warning(
                        "Removing %s from %s %s lineup — %s (%s)",
                        player_name, team, pos, inj.status, inj.details,
                    )
                    replacement = await _find_best_healthy_starter(
                        session, team, pos, injury_lookup,
                    )
                    lineup[pos] = replacement or ""
                    if replacement:
                        logger.info("Replaced with %s", replacement)
                    continue

                if not lineup["confirmed"]:
                    usual = await _find_best_healthy_starter(
                        session, team, pos, injury_lookup,
                    )
                    if usual and _normalize_name(usual) != _normalize_name(player_name):
                        logger.warning(
                            "Correcting %s %s: %s -> %s (usual starter is healthy)",
                            team, pos, player_name, usual,
                        )
                        lineup[pos] = usual

        await _resolve_abbreviated_names(session, lineups)

    return lineups


async def _resolve_abbreviated_names(
    session, lineups: list[dict],
) -> None:
    """Replace abbreviated Rotowire names (e.g. 'D. Clingan') with canonical
    Player names ('Donovan Clingan') so downstream matching is consistent."""
    for lineup in lineups:
        team = lineup["team"]
        for pos in _POSITIONS:
            name = lineup.get(pos, "")
            if not name:
                continue

            result = await session.execute(
                select(Player).where(
                    and_(Player.team == team, Player.name == name)
                )
            )
            if result.scalar_one_or_none():
                continue

            parts = name.strip().split()
            if len(parts) >= 2 and len(parts[0].rstrip(".")) == 1:
                initial = parts[0].rstrip(".").upper()
                last = " ".join(parts[1:])
                result = await session.execute(
                    select(Player).where(
                        and_(
                            Player.team == team,
                            Player.name.like(f"{initial}%{last}"),
                        )
                    )
                )
                match = result.scalar_one_or_none()
                if match:
                    logger.debug("Resolved %s -> %s", name, match.name)
                    lineup[pos] = match.name


async def _find_best_healthy_starter(
    session,
    team: str,
    position: str,
    injury_lookup: dict[tuple[str, str], InjuryReport],
) -> str | None:
    """Find the best healthy starter for a team/position.

    Search order:
    1. Flagged usual starter at exact position
    2. Flagged usual starter at adjacent positions (PF<->C, PG<->SG, etc.)
    3. Player at exact position with the most starts in recent games
    """
    positions_to_check = [position] + ADJACENT_POSITIONS.get(position, [])

    for pos in positions_to_check:
        result = await session.execute(
            select(Player).where(
                and_(
                    Player.team == team,
                    Player.position == pos,
                    Player.is_usual_starter == True,
                )
            )
        )
        for player in result.scalars().all():
            inj = _lookup_injury(injury_lookup, player.name, team)
            if not inj or inj.status not in ("Out", "Doubtful"):
                return player.name

    all_positions = set(positions_to_check + [position])
    most_starts = await session.execute(
        select(Player.name, func.count(GameLog.id).label("start_count"))
        .join(GameLog, GameLog.player_id == Player.id)
        .where(
            and_(
                Player.team == team,
                Player.position.in_(all_positions),
                GameLog.started == True,
            )
        )
        .group_by(Player.id)
        .order_by(func.count(GameLog.id).desc())
        .limit(5)
    )
    for row in most_starts:
        name, _ = row
        inj = _lookup_injury(injury_lookup, name, team)
        if not inj or inj.status not in ("Out", "Doubtful"):
            return name

    return None


async def get_todays_lineups() -> list[dict]:
    """Get today's stored lineups from the database."""
    today = date.today()
    async with async_session() as session:
        result = await session.execute(
            select(StartingLineup).where(StartingLineup.game_date == today)
        )
        lineups = result.scalars().all()
        return [
            {
                "team": lu.team,
                "opponent": lu.opponent,
                "PG": lu.pg,
                "SG": lu.sg,
                "SF": lu.sf,
                "PF": lu.pf,
                "C": lu.c,
                "confirmed": lu.confirmed,
            }
            for lu in lineups
        ]
