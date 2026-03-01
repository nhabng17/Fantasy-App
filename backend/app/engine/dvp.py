"""Defense vs Position (DvP) engine.

Calculates how many DK fantasy points each NBA team allows to each position
over their last 10 games. Teams that allow the most FP are the best matchups.
"""

import logging
from datetime import datetime, timedelta, date

from sqlalchemy import select, func, and_, desc
from sqlalchemy.dialects.sqlite import insert

from app.config import POSITIONS
from app.database import async_session
from app.models import GameLog, Player, TeamDefense

logger = logging.getLogger(__name__)

DVP_GRADES = {
    (1, 6): "A",   # top 6 = easiest matchup
    (7, 12): "B",
    (13, 18): "C",
    (19, 24): "D",
    (25, 30): "F", # bottom 6 = toughest matchup
}


async def calculate_dvp(num_games: int = 10) -> dict[str, dict[str, dict]]:
    """Calculate DvP for all teams and positions over the last N games.

    Returns: {
        team: {
            position: {
                "avg_fp_allowed": float,
                "rank": int,
                "grade": str,
                "games_sampled": int,
            }
        }
    }
    """
    results = {}

    async with async_session() as session:
        teams_result = await session.execute(
            select(Player.team).distinct().where(Player.team != "FA")
        )
        teams = [row[0] for row in teams_result]

        for position in POSITIONS:
            position_dvp = []

            for team in teams:
                avg_fp = await _calc_team_position_dvp(
                    session, team, position, num_games
                )
                if avg_fp is not None:
                    position_dvp.append((team, avg_fp))

            position_dvp.sort(key=lambda x: x[1], reverse=True)

            for rank, (team, avg_fp) in enumerate(position_dvp, 1):
                if team not in results:
                    results[team] = {}
                results[team][position] = {
                    "avg_fp_allowed": round(avg_fp, 1),
                    "rank": rank,
                    "grade": _rank_to_grade(rank),
                    "games_sampled": num_games,
                }

                stmt = insert(TeamDefense).values(
                    team=team,
                    position=position,
                    dk_fp_allowed_avg=round(avg_fp, 1),
                    rank=rank,
                    games_sampled=num_games,
                    last_updated=datetime.utcnow(),
                ).on_conflict_do_update(
                    index_elements=["team", "position"],
                    set_={
                        "dk_fp_allowed_avg": round(avg_fp, 1),
                        "rank": rank,
                        "games_sampled": num_games,
                        "last_updated": datetime.utcnow(),
                    },
                )
                await session.execute(stmt)

        await session.commit()

    logger.info(f"Calculated DvP for {len(teams)} teams across {len(POSITIONS)} positions")
    return results


async def _calc_team_position_dvp(
    session, team: str, position: str, num_games: int
) -> float | None:
    """Calculate avg DK FP allowed by a team to a specific position.

    Looks at what opposing players at that position scored against this team
    in the last N games.
    """
    recent_dates = await session.execute(
        select(GameLog.game_date)
        .where(GameLog.opponent == team)
        .distinct()
        .order_by(desc(GameLog.game_date))
        .limit(num_games)
    )
    game_dates = [row[0] for row in recent_dates]
    if not game_dates:
        return None

    result = await session.execute(
        select(func.avg(GameLog.dk_fp))
        .join(Player, Player.id == GameLog.player_id)
        .where(
            and_(
                GameLog.opponent == team,
                GameLog.game_date.in_(game_dates),
                Player.position == position,
                GameLog.started == True,
            )
        )
    )
    avg_fp = result.scalar()
    return float(avg_fp) if avg_fp else None


def _rank_to_grade(rank: int) -> str:
    for (low, high), grade in DVP_GRADES.items():
        if low <= rank <= high:
            return grade
    return "C"


async def get_dvp_for_matchup(team: str, position: str) -> dict | None:
    """Get DvP data for a specific team/position matchup."""
    async with async_session() as session:
        result = await session.execute(
            select(TeamDefense).where(
                and_(TeamDefense.team == team, TeamDefense.position == position)
            )
        )
        td = result.scalar_one_or_none()
        if td:
            return {
                "team": td.team,
                "position": td.position,
                "avg_fp_allowed": td.dk_fp_allowed_avg,
                "rank": td.rank,
                "grade": _rank_to_grade(td.rank),
            }
        return None
