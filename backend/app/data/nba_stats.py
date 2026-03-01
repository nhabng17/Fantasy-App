"""NBA stats client using nba_api for game logs, player info, and schedule data."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, date

import pandas as pd
from nba_api.stats.endpoints import (
    playergamelog,
    commonteamroster,
    scoreboardv2,
)
from nba_api.stats.static import teams as nba_teams
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.config import DK_SCORING, USUAL_STARTER_THRESHOLD
from app.database import async_session
from app.models import Player, GameLog

logger = logging.getLogger(__name__)

ALL_TEAMS = {t["abbreviation"]: t for t in nba_teams.get_teams()}
TEAM_ID_MAP = {t["id"]: t["abbreviation"] for t in nba_teams.get_teams()}

NBA_API_DELAY = 0.6  # seconds between requests to avoid rate limiting


def calc_dk_fantasy_points(row: dict) -> float:
    pts = row.get("pts", 0)
    reb = row.get("reb", 0)
    ast = row.get("ast", 0)
    stl = row.get("stl", 0)
    blk = row.get("blk", 0)
    tov = row.get("tov", 0)
    three_pm = row.get("three_pm", 0)

    fp = (
        pts * DK_SCORING["pts"]
        + three_pm * DK_SCORING["three_pm"]
        + reb * DK_SCORING["reb"]
        + ast * DK_SCORING["ast"]
        + stl * DK_SCORING["stl"]
        + blk * DK_SCORING["blk"]
        + tov * DK_SCORING["tov"]
    )

    stat_cats_over_10 = sum(1 for s in [pts, reb, ast, stl, blk] if s >= 10)
    if stat_cats_over_10 >= 3:
        fp += DK_SCORING["td_bonus"]
    if stat_cats_over_10 >= 2:
        fp += DK_SCORING["dd_bonus"]

    return round(fp, 2)


async def fetch_todays_games() -> list[dict]:
    """Get today's NBA games from the scoreboard."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        scoreboard = scoreboardv2.ScoreboardV2(game_date=today)
        games_df = scoreboard.get_data_frames()[0]

        games = []
        for _, row in games_df.iterrows():
            home_id = row["HOME_TEAM_ID"]
            away_id = row["VISITOR_TEAM_ID"]
            home_team = TEAM_ID_MAP.get(home_id)
            away_team = TEAM_ID_MAP.get(away_id)
            if home_team and away_team:
                games.append({
                    "game_id": row["GAME_ID"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "status": row.get("GAME_STATUS_TEXT", ""),
                })
        return games
    except Exception as e:
        logger.error(f"Failed to fetch today's games: {e}")
        return []


async def fetch_and_store_player_game_logs(
    season: str = "2025-26",
    teams_filter: list[str] | None = None,
):
    """Fetch game logs for players on specified teams (or today's teams).

    Instead of fetching ALL 600+ players, we fetch rosters team-by-team
    for only the teams playing today. This is faster and avoids rate limits.
    """
    try:
        if teams_filter is None:
            games = await fetch_todays_games()
            teams_filter = list({g["home_team"] for g in games} | {g["away_team"] for g in games})

        if not teams_filter:
            logger.warning("No teams to fetch -- no games today?")
            teams_filter = [t["abbreviation"] for t in nba_teams.get_teams()]

        total_players = 0
        total_logs = 0

        for team_abbrev in teams_filter:
            team_info = ALL_TEAMS.get(team_abbrev)
            if not team_info:
                continue

            logger.info(f"Fetching roster for {team_abbrev}...")
            try:
                roster = commonteamroster.CommonTeamRoster(
                    team_id=team_info["id"], season=season
                )
                roster_df = roster.get_data_frames()[0]
                time.sleep(NBA_API_DELAY)
            except Exception as e:
                logger.warning(f"Failed to fetch roster for {team_abbrev}: {e}")
                continue

            async with async_session() as session:
                for _, p_row in roster_df.iterrows():
                    nba_id = int(p_row["PLAYER_ID"])
                    name = p_row.get("PLAYER", "")
                    position = p_row.get("POSITION", "")

                    stmt = insert(Player).values(
                        nba_id=nba_id,
                        name=name,
                        team=team_abbrev,
                        position=_map_position(position),
                    ).on_conflict_do_update(
                        index_elements=["nba_id"],
                        set_={"name": name, "team": team_abbrev},
                    )
                    await session.execute(stmt)

                await session.commit()
                total_players += len(roster_df)

            for _, p_row in roster_df.iterrows():
                nba_id = int(p_row["PLAYER_ID"])
                logs_stored = await _fetch_player_logs(nba_id, season)
                total_logs += logs_stored
                time.sleep(NBA_API_DELAY)

            logger.info(f"  {team_abbrev}: {len(roster_df)} players processed")

        logger.info(f"NBA stats complete: {total_players} players, {total_logs} game logs across {len(teams_filter)} teams")
    except Exception as e:
        logger.error(f"Failed to fetch player game logs: {e}")


async def _fetch_player_logs(nba_id: int, season: str) -> int:
    """Fetch and store individual player game logs. Returns count of logs stored."""
    try:
        log = playergamelog.PlayerGameLog(player_id=nba_id, season=season)
        df = log.get_data_frames()[0]
        if df.empty:
            return 0

        async with async_session() as session:
            player_result = await session.execute(
                select(Player).where(Player.nba_id == nba_id)
            )
            player = player_result.scalar_one_or_none()
            if not player:
                return 0

            position = _extract_position(df)
            if position and not player.position:
                player.position = position

            starts = 0
            recent_games = 0
            total_minutes = 0.0
            stored = 0

            for _, row in df.iterrows():
                game_date = _parse_game_date(row["GAME_DATE"])
                if not game_date:
                    continue

                matchup = row.get("MATCHUP", "")
                opponent = _parse_opponent(matchup)
                minutes = _parse_minutes(row.get("MIN", 0))
                # PlayerGameLog doesn't include START_POSITION;
                # infer starter status from minutes (28+ min = likely starter)
                started = minutes >= 28.0

                stats = {
                    "pts": int(row.get("PTS", 0)),
                    "reb": int(row.get("REB", 0)),
                    "ast": int(row.get("AST", 0)),
                    "stl": int(row.get("STL", 0)),
                    "blk": int(row.get("BLK", 0)),
                    "tov": int(row.get("TOV", 0)),
                    "three_pm": int(row.get("FG3M", 0)),
                }

                dk_fp = calc_dk_fantasy_points(stats)

                stmt = insert(GameLog).values(
                    player_id=player.id,
                    game_date=game_date,
                    opponent=opponent,
                    minutes=minutes,
                    pts=stats["pts"],
                    reb=stats["reb"],
                    ast=stats["ast"],
                    stl=stats["stl"],
                    blk=stats["blk"],
                    tov=stats["tov"],
                    three_pm=stats["three_pm"],
                    started=started,
                    dk_fp=dk_fp,
                ).on_conflict_do_update(
                    index_elements=["player_id", "game_date"],
                    set_={
                        "minutes": minutes,
                        "pts": stats["pts"],
                        "reb": stats["reb"],
                        "ast": stats["ast"],
                        "stl": stats["stl"],
                        "blk": stats["blk"],
                        "tov": stats["tov"],
                        "three_pm": stats["three_pm"],
                        "started": started,
                        "dk_fp": dk_fp,
                    },
                )
                await session.execute(stmt)
                stored += 1

                if recent_games < 10:
                    recent_games += 1
                    total_minutes += minutes
                    if started:
                        starts += 1

            player.is_usual_starter = starts >= USUAL_STARTER_THRESHOLD
            if recent_games > 0:
                player.avg_minutes = round(total_minutes / recent_games, 1)

            await session.commit()
            return stored

    except Exception as e:
        logger.warning(f"Failed to fetch logs for player {nba_id}: {e}")
        return 0


def _map_position(pos: str) -> str:
    """Map NBA roster positions to DK-style positions."""
    pos = pos.upper().strip()
    if not pos:
        return ""
    mapping = {
        "G": "PG", "G-F": "SG", "F-G": "SF",
        "F": "SF", "F-C": "PF", "C-F": "C",
        "C": "C", "PG": "PG", "SG": "SG",
        "SF": "SF", "PF": "PF",
    }
    return mapping.get(pos, pos.split("-")[0] if "-" in pos else pos)


def _extract_position(df: pd.DataFrame) -> str:
    """PlayerGameLog doesn't have START_POSITION; position comes from roster."""
    return ""


def _parse_game_date(date_str: str) -> date | None:
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _parse_opponent(matchup: str) -> str:
    if not matchup:
        return ""
    parts = matchup.split(" ")
    return parts[-1] if parts else ""


def _parse_minutes(min_val) -> float:
    if isinstance(min_val, (int, float)):
        return float(min_val)
    if isinstance(min_val, str) and ":" in min_val:
        parts = min_val.split(":")
        return float(parts[0]) + float(parts[1]) / 60
    try:
        return float(min_val)
    except (ValueError, TypeError):
        return 0.0
