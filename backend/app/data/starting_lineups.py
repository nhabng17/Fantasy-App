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
from sqlalchemy import select, delete, and_
from sqlalchemy.dialects.sqlite import insert

from app.config import SCRAPE_HEADERS
from app.database import async_session
from app.models import StartingLineup, InjuryReport, Player

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


def _normalize_name(name: str) -> str:
    """Transliterate diacritics to ASCII and strip suffixes for matching."""
    ascii_name = "".join(
        c for c in unicodedata.normalize("NFKD", name)
        if unicodedata.category(c) != "Mn"
    )
    parts = [p for p in ascii_name.lower().split() if p not in _NAME_SUFFIXES]
    return " ".join(parts)


def _lookup_injury(
    injury_lookup: dict[tuple[str, str], InjuryReport],
    player_name: str,
    team: str,
) -> InjuryReport | None:
    """Find an injury report by player name + team with normalized fallback."""
    inj = injury_lookup.get((player_name.lower(), team))
    if inj:
        return inj
    return injury_lookup.get((_normalize_name(player_name), team))


async def _validate_lineups(lineups: list[dict]) -> list[dict]:
    """Cross-reference lineups with injury reports and usual starters.

    1. Remove Out/Doubtful players from lineup slots.
    2. For unconfirmed lineups, replace non-usual starters with the healthy
       usual starter when available (catches stale Rotowire data).
    """
    async with async_session() as session:
        injuries_result = await session.execute(select(InjuryReport))
        injury_lookup: dict[tuple[str, str], InjuryReport] = {}
        for inj in injuries_result.scalars().all():
            key = (inj.player_name.lower(), inj.team)
            injury_lookup[key] = inj
            norm_key = (_normalize_name(inj.player_name), inj.team)
            if norm_key not in injury_lookup:
                injury_lookup[norm_key] = inj

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
                    replacement = await _find_healthy_usual_starter(
                        session, team, pos, injury_lookup,
                    )
                    lineup[pos] = replacement or ""
                    if replacement:
                        logger.info(
                            "Replaced with usual starter %s", replacement,
                        )
                    continue

                if not lineup["confirmed"]:
                    usual = await _find_healthy_usual_starter(
                        session, team, pos, injury_lookup,
                    )
                    if usual and _normalize_name(usual) != _normalize_name(player_name):
                        logger.warning(
                            "Correcting %s %s: %s -> %s (usual starter is healthy)",
                            team, pos, player_name, usual,
                        )
                        lineup[pos] = usual

    return lineups


async def _find_healthy_usual_starter(
    session,
    team: str,
    position: str,
    injury_lookup: dict[tuple[str, str], InjuryReport],
) -> str | None:
    """Return the name of the usual starter if they exist and are healthy."""
    result = await session.execute(
        select(Player).where(
            and_(
                Player.team == team,
                Player.position == position,
                Player.is_usual_starter == True,
            )
        )
    )
    usual = result.scalar_one_or_none()
    if not usual:
        return None

    inj = _lookup_injury(injury_lookup, usual.name, team)
    if inj and inj.status in ("Out", "Doubtful"):
        return None

    return usual.name


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
