"""Scrape team depth charts from Hashtag Basketball."""

import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.config import SCRAPE_HEADERS

logger = logging.getLogger(__name__)

HASHTAG_DEPTH_URL = "https://hashtagbasketball.com/nba-depth-charts"


async def fetch_depth_charts() -> dict[str, dict]:
    """Scrape depth charts and return minutes distribution by team/position.

    Returns: {team_abbrev: {position: [{name, minutes_pct, role}]}}
    """
    try:
        async with httpx.AsyncClient(headers=SCRAPE_HEADERS, timeout=30) as client:
            resp = await client.get(HASHTAG_DEPTH_URL)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        depth = {}

        team_sections = soup.select("table, .depth-chart, [class*='depth']")

        for section in team_sections:
            parsed = _parse_depth_section(section)
            if parsed:
                team, positions = parsed
                depth[team] = positions

        if not depth:
            depth = _fallback_depth_parse(soup)

        logger.info(f"Parsed depth charts for {len(depth)} teams")
        return depth
    except Exception as e:
        logger.error(f"Failed to fetch depth charts: {e}")
        return {}


def _parse_depth_section(section) -> tuple[str, dict] | None:
    """Parse a single team's depth chart section."""
    header = section.find("th") or section.find("caption")
    if not header:
        return None

    team_name = header.get_text(strip=True)
    positions = {}
    rows = section.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 2:
            pos = cols[0].get_text(strip=True).upper()
            if pos in ("PG", "SG", "SF", "PF", "C"):
                players = []
                for i, col in enumerate(cols[1:]):
                    name = col.get_text(strip=True)
                    if name:
                        role = "starter" if i == 0 else "backup"
                        players.append({
                            "name": name,
                            "role": role,
                            "depth_order": i + 1,
                        })
                positions[pos] = players

    if positions:
        return team_name, positions
    return None


def _fallback_depth_parse(soup: BeautifulSoup) -> dict:
    """Fallback parser for depth charts."""
    depth = {}
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        for row in rows[1:]:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 2:
                pass  # structure varies; log for debugging

    return depth


def get_minutes_projection(depth: dict, team: str, position: str, player_name: str) -> float:
    """Estimate minutes for a player based on their depth chart position."""
    team_depth = depth.get(team, {})
    pos_depth = team_depth.get(position, [])

    base_minutes = {
        1: 32.0,  # starter
        2: 20.0,  # first backup
        3: 12.0,  # reserve
        4: 5.0,   # deep bench
    }

    for entry in pos_depth:
        if _name_match(entry["name"], player_name):
            return base_minutes.get(entry["depth_order"], 10.0)

    return 15.0  # default if not found


def _name_match(a: str, b: str) -> bool:
    """Fuzzy match player names (handles first/last name variations)."""
    a_parts = set(a.lower().split())
    b_parts = set(b.lower().split())
    return len(a_parts & b_parts) >= 1 and (
        a.lower() == b.lower() or len(a_parts & b_parts) / max(len(a_parts), len(b_parts)) > 0.5
    )
