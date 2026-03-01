"""Scrape injury reports from Rotowire's JSON API endpoint."""

import logging
from datetime import datetime

import httpx
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert

from app.config import SCRAPE_HEADERS
from app.database import async_session
from app.models import InjuryReport

logger = logging.getLogger(__name__)

ROTOWIRE_INJURIES_API = (
    "https://www.rotowire.com/basketball/tables/injury-report.php?team=ALL&pos=ALL"
)

POSITION_MAP = {
    "G": "PG",
    "F": "SF",
    "C": "C",
    "PG": "PG",
    "SG": "SG",
    "SF": "SF",
    "PF": "PF",
}


async def fetch_and_store_injuries() -> list[dict]:
    """Fetch injury data from Rotowire JSON API and store in database."""
    try:
        injuries = await _fetch_rotowire_injuries()
        if not injuries:
            logger.warning("No injuries fetched from Rotowire")
            return []

        async with async_session() as session:
            await session.execute(delete(InjuryReport))

            for inj in injuries:
                stmt = insert(InjuryReport).values(
                    player_id=0,
                    player_name=inj["player_name"],
                    team=inj["team"],
                    position=inj["position"],
                    status=inj["status"],
                    details=inj["details"],
                    last_updated=datetime.utcnow(),
                )
                await session.execute(stmt)

            await session.commit()
        logger.info(f"Stored {len(injuries)} injury reports")
        return injuries
    except Exception as e:
        logger.error(f"Failed to fetch injuries: {e}")
        return []


async def _fetch_rotowire_injuries() -> list[dict]:
    """Rotowire serves injury data as JSON from an AJAX endpoint."""
    async with httpx.AsyncClient(headers=SCRAPE_HEADERS, timeout=30) as client:
        resp = await client.get(ROTOWIRE_INJURIES_API)
        resp.raise_for_status()

    data = resp.json()
    injuries = []

    for entry in data:
        player_name = entry.get("player", "").strip()
        team = entry.get("team", "").strip()
        position = POSITION_MAP.get(entry.get("position", ""), entry.get("position", ""))
        raw_status = entry.get("status", "").strip()
        injury_type = entry.get("injury", "").strip()

        if not player_name:
            continue

        injuries.append({
            "player_name": player_name,
            "team": team,
            "position": position,
            "status": _normalize_status(raw_status),
            "details": injury_type,
        })

    return injuries


def _normalize_status(status: str) -> str:
    s = status.lower().strip()
    if "out for season" in s:
        return "Out"
    if "out" in s:
        return "Out"
    if "doubtful" in s:
        return "Doubtful"
    if "questionable" in s:
        return "GTD"
    if "probable" in s:
        return "Probable"
    if "day-to-day" in s or "gtd" in s:
        return "GTD"
    return status
