"""Core projection engine.

Combines all signals (DvP, spot starts, depth, injuries, ownership)
into a final projected DK fantasy point total and value score per player.
"""

import logging
import unicodedata
from datetime import datetime, date

from sqlalchemy import select, and_, func, delete as sa_delete
from sqlalchemy.dialects.sqlite import insert

from app.config import DK_SCORING, POSITIONS, MAX_VALUE_SALARY
from app.database import async_session
from app.models import (
    Player, GameLog, TeamDefense, InjuryReport,
    StartingLineup, SpotStart, Projection,
)
from app.engine.dvp import _rank_to_grade

logger = logging.getLogger(__name__)

WEIGHTS = {
    "dvp": 0.30,
    "base_minutes": 0.20,
    "spot_start": 0.25,
    "injury_usage": 0.10,
    "ownership": 0.15,
}


async def generate_projections(
    games: list[dict] | None = None,
) -> list[dict]:
    """Generate projections for all players in today's games.

    Args:
        games: List of today's games [{home_team, away_team}].
               If None, projects all rostered players.
    """
    today = date.today()
    projections = []

    async with async_session() as session:
        if games:
            teams_playing = set()
            matchups = {}
            for g in games:
                teams_playing.add(g["home_team"])
                teams_playing.add(g["away_team"])
                matchups[g["home_team"]] = g["away_team"]
                matchups[g["away_team"]] = g["home_team"]
        else:
            teams_result = await session.execute(
                select(Player.team).distinct().where(Player.team != "FA")
            )
            teams_playing = {r[0] for r in teams_result}
            matchups = {}

        players_result = await session.execute(
            select(Player).where(Player.team.in_(teams_playing))
        )
        players = players_result.scalars().all()

        spot_starts = await session.execute(
            select(SpotStart).where(SpotStart.game_date == today)
        )
        spot_start_map = {s.player_id: s for s in spot_starts.scalars().all()}

        injuries = await session.execute(select(InjuryReport))
        injury_map = {}
        for inj in injuries.scalars().all():
            injury_map[inj.player_name.lower()] = inj
            normalized = _normalize_name(inj.player_name)
            if normalized not in injury_map:
                injury_map[normalized] = inj

        lineups = await session.execute(
            select(StartingLineup).where(StartingLineup.game_date == today)
        )
        lineup_map = {lu.team: lu for lu in lineups.scalars().all()}

        out_player_ids = []
        for player in players:
            inj = _find_injury(injury_map, player.name)
            if inj and inj.status in ("Out", "Doubtful"):
                out_player_ids.append(player.id)
                continue

            opponent = matchups.get(player.team, "")
            injury_status = inj.status if inj else ""
            proj = await _project_player(
                session, player, opponent, spot_start_map,
                injury_map, lineup_map, today, injury_status,
            )
            if proj:
                projections.append(proj)

                stmt = insert(Projection).values(
                    player_id=player.id,
                    player_name=player.name,
                    team=player.team,
                    position=player.position,
                    opponent=opponent,
                    salary=player.salary,
                    projected_fp=proj["projected_fp"],
                    dvp_score=proj["dvp_score"],
                    dvp_grade=proj["dvp_grade"],
                    depth_score=proj["depth_score"],
                    injury_boost=proj["injury_boost"],
                    spot_start_boost=proj["spot_start_boost"],
                    ownership_pct=proj["ownership_pct"],
                    value_score=proj["value_score"],
                    fp_per_dollar=proj["fp_per_dollar"],
                    is_spot_starter=proj["is_spot_starter"],
                    is_confirmed_starter=proj["is_confirmed_starter"],
                    minutes_projection=proj["minutes_projection"],
                    injury_status=proj["injury_status"],
                    last_updated=datetime.utcnow(),
                ).on_conflict_do_update(
                    index_elements=["player_id"],
                    set_={
                        "opponent": opponent,
                        "salary": player.salary,
                        "projected_fp": proj["projected_fp"],
                        "dvp_score": proj["dvp_score"],
                        "dvp_grade": proj["dvp_grade"],
                        "depth_score": proj["depth_score"],
                        "injury_boost": proj["injury_boost"],
                        "spot_start_boost": proj["spot_start_boost"],
                        "ownership_pct": proj["ownership_pct"],
                        "value_score": proj["value_score"],
                        "fp_per_dollar": proj["fp_per_dollar"],
                        "is_spot_starter": proj["is_spot_starter"],
                        "is_confirmed_starter": proj["is_confirmed_starter"],
                        "minutes_projection": proj["minutes_projection"],
                        "injury_status": proj["injury_status"],
                        "last_updated": datetime.utcnow(),
                    },
                )
                await session.execute(stmt)

        if out_player_ids:
            await session.execute(
                sa_delete(Projection).where(Projection.player_id.in_(out_player_ids))
            )
            logger.info(f"Removed {len(out_player_ids)} projections for Out/Doubtful players")

        await session.commit()

    projections.sort(key=lambda x: x["projected_fp"], reverse=True)
    logger.info(f"Generated {len(projections)} projections")
    return projections


async def _project_player(
    session, player: Player, opponent: str,
    spot_start_map: dict, injury_map: dict,
    lineup_map: dict, today: date,
    injury_status: str = "",
) -> dict | None:
    """Generate projection for a single player."""
    recent_logs = await session.execute(
        select(GameLog)
        .where(GameLog.player_id == player.id)
        .order_by(GameLog.game_date.desc())
        .limit(10)
    )
    logs = recent_logs.scalars().all()

    if not logs:
        return None

    base_avg = sum(g.dk_fp for g in logs) / len(logs) if logs else 0
    avg_minutes = sum(g.minutes for g in logs) / len(logs) if logs else 0

    # --- DvP component ---
    dvp_score = 0.0
    dvp_grade = "C"
    if opponent:
        dvp_result = await session.execute(
            select(TeamDefense).where(
                and_(
                    TeamDefense.team == opponent,
                    TeamDefense.position == player.position,
                )
            )
        )
        dvp = dvp_result.scalar_one_or_none()
        if dvp:
            league_avg = 30.0  # approximate league avg DK FP for starters
            dvp_score = (dvp.dk_fp_allowed_avg - league_avg) / league_avg
            dvp_grade = _rank_to_grade(dvp.rank)

    # --- Spot start component ---
    spot_start_boost = 0.0
    is_spot_starter = False
    spot = spot_start_map.get(player.id)
    if spot:
        is_spot_starter = True
        if spot.historical_spot_avg_fp > 0:
            spot_start_boost = (spot.historical_spot_avg_fp - base_avg) / max(base_avg, 1)
        else:
            spot_start_boost = 0.3  # default 30% bump for starting

    # --- Confirmed starter check ---
    is_confirmed_starter = player.is_usual_starter
    lineup = lineup_map.get(player.team)
    if lineup:
        starters = [lineup.pg, lineup.sg, lineup.sf, lineup.pf, lineup.c]
        if player.name in starters:
            is_confirmed_starter = True

    # --- Injury-driven usage bump ---
    injury_boost = 0.0
    team_injuries = [
        inj for inj in injury_map.values()
        if inj.team == player.team and inj.status in ("Out", "Doubtful")
    ]
    if team_injuries and not is_spot_starter:
        for inj in team_injuries:
            if inj.position == player.position:
                injury_boost += 0.10  # 10% bump per injured player at same position
            elif inj.position in POSITIONS:
                injury_boost += 0.03  # small bump for any injured teammate

    # --- Minutes projection ---
    if is_spot_starter and spot:
        minutes_proj = spot.projected_minutes
    elif is_confirmed_starter:
        minutes_proj = avg_minutes
    else:
        minutes_proj = avg_minutes * 0.9  # slight decrease if unconfirmed

    minutes_factor = minutes_proj / max(avg_minutes, 1) if avg_minutes > 0 else 1.0

    # --- Depth score (minutes stability) ---
    if len(logs) >= 5:
        min_variance = sum((g.minutes - avg_minutes) ** 2 for g in logs) / len(logs)
        depth_score = 1.0 - min(min_variance / 100, 0.5)
    else:
        depth_score = 0.5

    # --- Combine all factors ---
    projected_fp = base_avg * (
        1
        + dvp_score * WEIGHTS["dvp"]
        + spot_start_boost * WEIGHTS["spot_start"]
        + injury_boost * WEIGHTS["injury_usage"]
    ) * (minutes_factor ** WEIGHTS["base_minutes"])

    projected_fp = max(projected_fp, 0)

    salary = player.salary or 0
    rounded_fp = round(projected_fp, 1)

    if salary > 0:
        value_score = round(rounded_fp / (salary / 1000), 2)
        fp_per_dollar = round(rounded_fp / salary, 4)
    else:
        value_score = 0.0
        fp_per_dollar = 0.0

    return {
        "player_id": player.id,
        "player_name": player.name,
        "team": player.team,
        "position": player.position,
        "opponent": opponent,
        "salary": salary,
        "projected_fp": rounded_fp,
        "dvp_score": round(dvp_score, 3),
        "dvp_grade": dvp_grade,
        "depth_score": round(depth_score, 2),
        "injury_boost": round(injury_boost, 3),
        "spot_start_boost": round(spot_start_boost, 3),
        "ownership_pct": 0.0,  # filled in by ownership pass
        "value_score": value_score,
        "fp_per_dollar": fp_per_dollar,
        "is_spot_starter": is_spot_starter,
        "is_confirmed_starter": is_confirmed_starter,
        "minutes_projection": round(minutes_proj, 1),
        "injury_status": injury_status,
    }


async def apply_ownership(ownership_data: dict[str, float]):
    """Update projections with ownership percentages and adjust value scores."""
    async with async_session() as session:
        projections = await session.execute(select(Projection))
        for proj in projections.scalars().all():
            name_lower = proj.player_name.lower()
            for own_name, pct in ownership_data.items():
                if own_name.lower() == name_lower or _fuzzy_match(own_name, proj.player_name):
                    proj.ownership_pct = pct

                    # Leverage score: lower ownership in good spots = more valuable
                    if pct < 10 and proj.projected_fp > 25:
                        proj.value_score *= 1.15  # 15% boost for low-owned gems
                    elif pct > 40:
                        proj.value_score *= 0.95  # slight penalty for chalk
                    break

        await session.commit()


_NAME_SUFFIXES = {"jr.", "jr", "sr.", "sr", "ii", "iii", "iv", "v"}


def _normalize_name(name: str) -> str:
    """Transliterate diacritics to ASCII and strip suffixes for cross-source matching."""
    ascii_name = "".join(
        c for c in unicodedata.normalize("NFKD", name)
        if unicodedata.category(c) != "Mn"
    )
    parts = [p for p in ascii_name.lower().split() if p not in _NAME_SUFFIXES]
    return " ".join(parts)


def _find_injury(injury_map: dict, player_name: str) -> object | None:
    """Look up a player in the injury map, falling back to suffix-stripped matching."""
    inj = injury_map.get(player_name.lower())
    if inj:
        return inj
    return injury_map.get(_normalize_name(player_name))


def _fuzzy_match(a: str, b: str) -> bool:
    a_parts = set(a.lower().split())
    b_parts = set(b.lower().split())
    return len(a_parts & b_parts) >= 2
