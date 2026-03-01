"""Scrape projected ownership percentages from RotoGrinders."""

import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.config import SCRAPE_HEADERS

logger = logging.getLogger(__name__)

ROTOGRINDERS_URL = "https://rotogrinders.com/projected-ownership/nba?site=draftkings"


async def fetch_ownership_projections() -> dict[str, float]:
    """Scrape projected DraftKings ownership percentages.

    Returns: {player_name: ownership_pct}
    """
    try:
        async with httpx.AsyncClient(
            headers=SCRAPE_HEADERS, timeout=30, follow_redirects=True
        ) as client:
            resp = await client.get(ROTOGRINDERS_URL)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        ownership = {}

        rows = soup.select(
            ".projected-ownership-table tr, "
            "table tbody tr, "
            "[class*='ownership'] tr"
        )

        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                name_el = cols[0].find("a") or cols[0]
                name = name_el.get_text(strip=True)
                pct_text = ""

                for col in cols[1:]:
                    text = col.get_text(strip=True)
                    if "%" in text:
                        pct_text = text
                        break

                if name and pct_text:
                    try:
                        pct = float(pct_text.replace("%", "").strip())
                        ownership[name] = pct
                    except ValueError:
                        pass

        if not ownership:
            ownership = _fallback_parse(soup)

        logger.info(f"Parsed ownership for {len(ownership)} players")
        return ownership
    except Exception as e:
        logger.error(f"Failed to fetch ownership projections: {e}")
        return {}


def _fallback_parse(soup: BeautifulSoup) -> dict[str, float]:
    """Fallback: look for JSON data or script tags with ownership data."""
    import json
    import re

    scripts = soup.find_all("script")
    for script in scripts:
        text = script.string or ""
        match = re.search(r'ownership["\s]*[:=]\s*(\[.*?\])', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                result = {}
                for item in data:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("player_name", "")
                        pct = item.get("ownership") or item.get("projected", 0)
                        if name and pct:
                            result[name] = float(pct)
                return result
            except (json.JSONDecodeError, ValueError):
                pass

    return {}
