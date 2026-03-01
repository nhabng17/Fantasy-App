"""FastAPI REST and WebSocket endpoints."""

from datetime import date

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select, and_

from app.config import POSITIONS
from app.database import async_session
from app.models import Projection, TeamDefense, InjuryReport, StartingLineup, SpotStart, Player
from app.ws_manager import manager

router = APIRouter()


@router.get("/projections")
async def get_projections(
    position: str | None = Query(None, description="Filter by position (PG, SG, SF, PF, C)"),
    sort_by: str = Query("projected_fp", description="Sort field"),
    limit: int = Query(50, le=200),
    spot_starts_only: bool = Query(False),
    min_salary: int | None = Query(None),
    max_salary: int | None = Query(None),
):
    """Get player projections, optionally filtered by position."""
    async with async_session() as session:
        query = select(Projection)

        if position and position.upper() in POSITIONS:
            query = query.where(Projection.position == position.upper())

        if spot_starts_only:
            query = query.where(Projection.is_spot_starter == True)

        if min_salary is not None:
            query = query.where(Projection.salary >= min_salary)

        if max_salary is not None:
            query = query.where(Projection.salary <= max_salary)

        sort_col = getattr(Projection, sort_by, Projection.projected_fp)
        query = query.order_by(sort_col.desc()).limit(limit)

        result = await session.execute(query)
        projections = result.scalars().all()

        return [_projection_to_dict(p) for p in projections]


@router.get("/dvp")
async def get_dvp(
    position: str | None = Query(None, description="Filter by position"),
):
    """Get Defense vs Position rankings."""
    async with async_session() as session:
        query = select(TeamDefense)

        if position and position.upper() in POSITIONS:
            query = query.where(TeamDefense.position == position.upper())

        query = query.order_by(TeamDefense.dk_fp_allowed_avg.desc())
        result = await session.execute(query)
        records = result.scalars().all()

        return [
            {
                "team": r.team,
                "position": r.position,
                "avg_fp_allowed": r.dk_fp_allowed_avg,
                "rank": r.rank,
                "games_sampled": r.games_sampled,
            }
            for r in records
        ]


@router.get("/injuries")
async def get_injuries():
    """Get current injury report."""
    async with async_session() as session:
        result = await session.execute(
            select(InjuryReport).order_by(InjuryReport.team)
        )
        injuries = result.scalars().all()

        return [
            {
                "player_name": inj.player_name,
                "team": inj.team,
                "position": inj.position,
                "status": inj.status,
                "details": inj.details,
                "last_updated": inj.last_updated.isoformat() if inj.last_updated else None,
            }
            for inj in injuries
        ]


@router.get("/lineups")
async def get_lineups():
    """Get today's starting lineups."""
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
                "last_updated": lu.last_updated.isoformat() if lu.last_updated else None,
            }
            for lu in lineups
        ]


@router.get("/spot-starts")
async def get_spot_starts():
    """Get today's spot start alerts, sorted by value."""
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
                "is_value_play": s.salary <= 4500 and s.historical_spot_avg_fp >= 20,
            }
            for s in spots
        ]


@router.get("/players/{player_id}")
async def get_player_detail(player_id: int):
    """Get detailed player info including projection breakdown and game logs."""
    async with async_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            return {"error": "Player not found"}

        proj_result = await session.execute(
            select(Projection).where(Projection.player_id == player_id)
        )
        projection = proj_result.scalar_one_or_none()

        from app.models import GameLog
        logs_result = await session.execute(
            select(GameLog)
            .where(GameLog.player_id == player_id)
            .order_by(GameLog.game_date.desc())
            .limit(10)
        )
        logs = logs_result.scalars().all()

        today = date.today()
        spot_result = await session.execute(
            select(SpotStart).where(
                and_(SpotStart.player_id == player_id, SpotStart.game_date == today)
            )
        )
        spot = spot_result.scalar_one_or_none()

        return {
            "player": {
                "id": player.id,
                "name": player.name,
                "team": player.team,
                "position": player.position,
                "salary": player.salary,
                "avg_minutes": player.avg_minutes,
                "is_usual_starter": player.is_usual_starter,
            },
            "projection": _projection_to_dict(projection) if projection else None,
            "spot_start": {
                "replacing": spot.replacing_player,
                "projected_minutes": spot.projected_minutes,
                "historical_avg_fp": spot.historical_spot_avg_fp,
                "prior_spot_starts": spot.spot_start_count,
                "value_score": spot.value_score,
                "confidence": spot.confidence,
            } if spot else None,
            "recent_games": [
                {
                    "date": log.game_date.isoformat(),
                    "opponent": log.opponent,
                    "minutes": log.minutes,
                    "pts": log.pts,
                    "reb": log.reb,
                    "ast": log.ast,
                    "stl": log.stl,
                    "blk": log.blk,
                    "tov": log.tov,
                    "three_pm": log.three_pm,
                    "dk_fp": log.dk_fp,
                    "started": log.started,
                }
                for log in logs
            ],
        }


@router.post("/refresh")
async def manual_refresh():
    """Manually trigger a full data refresh. Returns status of each step."""
    from app.scheduler import (
        refresh_injuries, refresh_lineups, refresh_nba_stats,
        refresh_ownership, refresh_dk_salaries, _regenerate_projections,
    )
    import traceback

    results = {}

    for name, fn in [
        ("injuries", refresh_injuries),
        ("lineups", refresh_lineups),
        ("dk_salaries", refresh_dk_salaries),
        ("nba_stats", refresh_nba_stats),
        ("ownership", refresh_ownership),
        ("projections", _regenerate_projections),
    ]:
        try:
            await fn()
            results[name] = "ok"
        except Exception as e:
            results[name] = f"error: {e}"

    async with async_session() as session:
        from sqlalchemy import func
        player_count = (await session.execute(select(func.count(Player.id)))).scalar() or 0
        proj_count = (await session.execute(select(func.count(Projection.id)))).scalar() or 0
        injury_count = (await session.execute(select(func.count(InjuryReport.id)))).scalar() or 0
        lineup_count = (await session.execute(select(func.count(StartingLineup.id)))).scalar() or 0

    return {
        "results": results,
        "db_counts": {
            "players": player_count,
            "projections": proj_count,
            "injuries": injury_count,
            "lineups": lineup_count,
        },
    }


@router.get("/health")
async def health_check():
    """Quick health check showing DB record counts."""
    async with async_session() as session:
        from sqlalchemy import func
        from app.models import GameLog
        counts = {}
        for model, name in [
            (Player, "players"), (GameLog, "game_logs"),
            (Projection, "projections"), (InjuryReport, "injuries"),
            (StartingLineup, "lineups"), (SpotStart, "spot_starts"),
            (TeamDefense, "team_defense"),
        ]:
            counts[name] = (await session.execute(select(func.count(model.id)))).scalar() or 0

    return {"status": "ok", "db_counts": counts}


@router.websocket("/ws/projections")
async def websocket_projections(websocket: WebSocket):
    """WebSocket endpoint for real-time projection updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def _projection_to_dict(p: Projection) -> dict:
    return {
        "player_id": p.player_id,
        "player_name": p.player_name,
        "team": p.team,
        "position": p.position,
        "opponent": p.opponent,
        "salary": p.salary,
        "projected_fp": p.projected_fp,
        "dvp_score": p.dvp_score,
        "dvp_grade": p.dvp_grade,
        "depth_score": p.depth_score,
        "injury_boost": p.injury_boost,
        "spot_start_boost": p.spot_start_boost,
        "ownership_pct": p.ownership_pct,
        "value_score": p.value_score,
        "fp_per_dollar": p.fp_per_dollar or 0.0,
        "is_spot_starter": p.is_spot_starter,
        "is_confirmed_starter": p.is_confirmed_starter,
        "minutes_projection": p.minutes_projection,
        "injury_status": p.injury_status or "",
        "last_updated": p.last_updated.isoformat() if p.last_updated else None,
    }
