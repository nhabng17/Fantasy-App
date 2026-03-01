"""Spot start detection and historical performance analysis.

Identifies bench players elevated to the starting lineup, calculates their
historical performance in spot start situations, and flags cheap/min-price
players as high-value plays.
"""

import logging
from datetime import datetime, date

from sqlalchemy import select, func, and_
from sqlalchemy.dialects.sqlite import insert

from app.config import MIN_SALARY, MAX_VALUE_SALARY, USUAL_STARTER_THRESHOLD
from app.database import async_session
from app.models import Player, GameLog, StartingLineup, SpotStart

logger = logging.getLogger(__name__)


async def detect_spot_starts() -> list[dict]:
    """Compare today's confirmed lineups against usual starters.

    Flags any player in the starting lineup who is NOT a usual starter
    as a spot starter. Calculates their historical spot start performance.
    """
    today = date.today()
    spot_starts = []

    async with async_session() as session:
        lineups_result = await session.execute(
            select(StartingLineup).where(StartingLineup.game_date == today)
        )
        lineups = lineups_result.scalars().all()

        for lineup in lineups:
            positions_in_lineup = {
                "PG": lineup.pg,
                "SG": lineup.sg,
                "SF": lineup.sf,
                "PF": lineup.pf,
                "C": lineup.c,
            }

            for pos, player_name in positions_in_lineup.items():
                if not player_name:
                    continue

                player = await _find_player(session, player_name, lineup.team)
                if not player:
                    continue

                if player.is_usual_starter:
                    continue

                usual_starter = await _find_usual_starter(
                    session, lineup.team, pos
                )

                spot_data = await _analyze_spot_start_history(session, player)

                minutes_proj = await _project_spot_minutes(
                    session, player, usual_starter
                )

                salary = player.salary or 0
                value = (
                    spot_data["avg_fp"] / (salary / 1000)
                    if salary > 0 and spot_data["avg_fp"] > 0
                    else 0.0
                )

                confidence = "Confirmed" if lineup.confirmed else "Expected"

                spot = {
                    "player_id": player.id,
                    "player_name": player.name,
                    "team": lineup.team,
                    "position": pos,
                    "game_date": today,
                    "replacing_player": usual_starter.name if usual_starter else "",
                    "salary": salary,
                    "projected_minutes": minutes_proj,
                    "historical_spot_avg_fp": spot_data["avg_fp"],
                    "spot_start_count": spot_data["count"],
                    "value_score": round(value, 2),
                    "confidence": confidence,
                    "is_value_play": salary <= MAX_VALUE_SALARY and spot_data["avg_fp"] >= 20,
                    "season_avg_fp": spot_data["season_avg"],
                    "spot_start_upside": spot_data["upside"],
                }

                stmt = insert(SpotStart).values(
                    player_id=player.id,
                    player_name=player.name,
                    team=lineup.team,
                    position=pos,
                    game_date=today,
                    replacing_player=usual_starter.name if usual_starter else "",
                    salary=salary,
                    projected_minutes=minutes_proj,
                    historical_spot_avg_fp=spot_data["avg_fp"],
                    spot_start_count=spot_data["count"],
                    value_score=round(value, 2),
                    confidence=confidence,
                    last_updated=datetime.utcnow(),
                ).on_conflict_do_update(
                    index_elements=["player_id", "game_date"],
                    set_={
                        "replacing_player": usual_starter.name if usual_starter else "",
                        "projected_minutes": minutes_proj,
                        "historical_spot_avg_fp": spot_data["avg_fp"],
                        "spot_start_count": spot_data["count"],
                        "value_score": round(value, 2),
                        "confidence": confidence,
                        "last_updated": datetime.utcnow(),
                    },
                )
                await session.execute(stmt)
                spot_starts.append(spot)

        await session.commit()

    logger.info(f"Detected {len(spot_starts)} spot starts")
    return spot_starts


async def _find_player(session, name: str, team: str) -> Player | None:
    """Find a player by name and team, with fuzzy matching."""
    result = await session.execute(
        select(Player).where(
            and_(Player.team == team, Player.name == name)
        )
    )
    player = result.scalar_one_or_none()

    if not player:
        result = await session.execute(
            select(Player).where(
                and_(Player.team == team, Player.name.ilike(f"%{name}%"))
            )
        )
        player = result.scalar_one_or_none()

    return player


async def _find_usual_starter(session, team: str, position: str) -> Player | None:
    """Find the usual starter for a team/position."""
    result = await session.execute(
        select(Player).where(
            and_(
                Player.team == team,
                Player.position == position,
                Player.is_usual_starter == True,
            )
        )
    )
    return result.scalar_one_or_none()


async def _analyze_spot_start_history(session, player: Player) -> dict:
    """Analyze a player's historical performance in spot start situations.

    A "spot start" game is one where the player started but is NOT a usual starter.
    """
    # All games where this non-usual-starter started
    spot_games = await session.execute(
        select(GameLog).where(
            and_(
                GameLog.player_id == player.id,
                GameLog.started == True,
            )
        )
    )
    spot_logs = spot_games.scalars().all()

    all_games = await session.execute(
        select(GameLog).where(GameLog.player_id == player.id)
    )
    all_logs = all_games.scalars().all()

    season_avg = (
        sum(g.dk_fp for g in all_logs) / len(all_logs) if all_logs else 0.0
    )

    if spot_logs:
        spot_fps = [g.dk_fp for g in spot_logs]
        avg_fp = sum(spot_fps) / len(spot_fps)
        upside = max(spot_fps)
    else:
        avg_fp = season_avg * 1.3  # estimate 30% bump for starting
        upside = season_avg * 1.8

    return {
        "avg_fp": round(avg_fp, 1),
        "count": len(spot_logs),
        "season_avg": round(season_avg, 1),
        "upside": round(upside, 1),
    }


async def _project_spot_minutes(
    session, player: Player, absent_starter: Player | None
) -> float:
    """Project minutes for a spot starter based on the absent starter's usage."""
    if absent_starter and absent_starter.avg_minutes > 0:
        starter_minutes = absent_starter.avg_minutes
        player_usual = player.avg_minutes or 15.0
        projected = min(starter_minutes, player_usual + (starter_minutes - player_usual) * 0.7)
        return round(max(projected, player_usual), 1)

    return round((player.avg_minutes or 15.0) * 1.5, 1)


async def get_spot_starts_for_today() -> list[dict]:
    """Get all spot starts detected for today."""
    today = date.today()
    async with async_session() as session:
        result = await session.execute(
            select(SpotStart)
            .where(SpotStart.game_date == today)
            .order_by(SpotStart.value_score.desc())
        )
        spots = result.scalars().all()
        return [
            {
                "player_name": s.player_name,
                "team": s.team,
                "position": s.position,
                "replacing_player": s.replacing_player,
                "salary": s.salary,
                "projected_minutes": s.projected_minutes,
                "historical_spot_avg_fp": s.historical_spot_avg_fp,
                "spot_start_count": s.spot_start_count,
                "value_score": s.value_score,
                "confidence": s.confidence,
            }
            for s in spots
        ]
