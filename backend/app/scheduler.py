"""APScheduler jobs for periodic data fetching and projection updates."""

import asyncio
import logging
import traceback

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import SCHEDULE_INTERVALS

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

scheduler = AsyncIOScheduler()


async def refresh_nba_stats():
    """Fetch latest game logs and recalculate DvP."""
    logger.info("Refreshing NBA stats...")
    try:
        from app.data.nba_stats import fetch_and_store_player_game_logs
        await fetch_and_store_player_game_logs()

        from app.engine.dvp import calculate_dvp
        await calculate_dvp()

        logger.info("NBA stats refresh complete")
    except Exception as e:
        logger.error(f"NBA stats refresh failed: {e}")


async def refresh_injuries():
    """Fetch latest injury reports and broadcast updates."""
    logger.info("Refreshing injury reports...")
    try:
        from app.data.injuries import fetch_and_store_injuries
        injuries = await fetch_and_store_injuries()

        if injuries:
            from app.ws_manager import manager
            for inj in injuries:
                if inj.get("status") in ("Out", "Doubtful"):
                    await manager.broadcast_injury(inj)

        logger.info("Injury refresh complete")
    except Exception as e:
        logger.error(f"Injury refresh failed: {e}")


async def refresh_lineups():
    """Fetch starting lineups and detect spot starts."""
    logger.info("Refreshing starting lineups...")
    try:
        from app.data.starting_lineups import fetch_and_store_lineups
        lineups = await fetch_and_store_lineups()

        from app.engine.spot_start import detect_spot_starts
        spot_starts = await detect_spot_starts()

        from app.ws_manager import manager

        if lineups:
            for lineup in lineups:
                await manager.broadcast_lineup_update(lineup)

        for spot in spot_starts:
            await manager.broadcast_spot_start(spot)

        await _regenerate_projections()

        logger.info(f"Lineup refresh complete: {len(lineups)} lineups, {len(spot_starts)} spot starts")
    except Exception as e:
        logger.error(f"Lineup refresh failed: {e}")


async def refresh_dk_salaries():
    """Fetch DraftKings salary data for today's slate."""
    logger.info("Refreshing DraftKings salaries...")
    try:
        from app.data.dk_salaries import fetch_and_store_dk_salaries
        matched = await fetch_and_store_dk_salaries()
        logger.info(f"DK salary refresh complete: {matched} players updated")
    except Exception as e:
        logger.error(f"DK salary refresh failed: {e}")


async def refresh_ownership():
    """Fetch ownership projections and apply to projections."""
    logger.info("Refreshing ownership projections...")
    try:
        from app.data.ownership import fetch_ownership_projections
        ownership = await fetch_ownership_projections()

        if ownership:
            from app.engine.projector import apply_ownership
            await apply_ownership(ownership)

        logger.info(f"Ownership refresh complete: {len(ownership)} players")
    except Exception as e:
        logger.error(f"Ownership refresh failed: {e}")


async def refresh_depth_charts():
    """Fetch latest depth charts."""
    logger.info("Refreshing depth charts...")
    try:
        from app.data.depth_charts import fetch_depth_charts
        depth = await fetch_depth_charts()
        logger.info(f"Depth chart refresh complete: {len(depth)} teams")
    except Exception as e:
        logger.error(f"Depth chart refresh failed: {e}")


async def _regenerate_projections():
    """Regenerate all projections and broadcast updates."""
    try:
        from app.data.nba_stats import fetch_todays_games
        from app.engine.projector import generate_projections
        from app.ws_manager import manager

        games = await fetch_todays_games()
        projections = await generate_projections(games)

        if projections:
            await manager.broadcast_projections(projections[:50])
    except Exception as e:
        logger.error(f"Projection regeneration failed: {e}")


async def _run_with_retries(name: str, fn, max_retries: int = 3, delay: int = 30):
    """Run a fetch function with retries on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            await fn()
            logger.info(f"{name} succeeded on attempt {attempt}")
            return
        except Exception as e:
            logger.error(f"{name} failed (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                logger.info(f"Retrying {name} in {delay}s...")
                await asyncio.sleep(delay)
    logger.error(f"{name} failed after {max_retries} attempts")


async def run_initial_fetch():
    """Run all data fetches immediately on startup with retries."""
    logger.info("=== Running initial data fetch ===")

    await _run_with_retries("injuries", refresh_injuries)
    await _run_with_retries("lineups", refresh_lineups)
    await _run_with_retries("dk_salaries", refresh_dk_salaries)
    await _run_with_retries("nba_stats", refresh_nba_stats, max_retries=3, delay=60)
    await _run_with_retries("ownership", refresh_ownership)
    await _run_with_retries("depth_charts", refresh_depth_charts)

    await _regenerate_projections()

    logger.info("=== Initial data fetch complete ===")


def start_scheduler():
    """Start all scheduled jobs and trigger an immediate initial fetch."""
    scheduler.add_job(
        refresh_nba_stats,
        "interval",
        seconds=SCHEDULE_INTERVALS["nba_stats"],
        id="nba_stats",
        name="NBA Stats Refresh",
    )
    scheduler.add_job(
        refresh_injuries,
        "interval",
        seconds=SCHEDULE_INTERVALS["injuries"],
        id="injuries",
        name="Injury Report Refresh",
    )
    scheduler.add_job(
        refresh_lineups,
        "interval",
        seconds=SCHEDULE_INTERVALS["starting_lineups"],
        id="starting_lineups",
        name="Starting Lineups Refresh",
    )
    scheduler.add_job(
        refresh_dk_salaries,
        "interval",
        seconds=SCHEDULE_INTERVALS.get("dk_salaries", 3600),
        id="dk_salaries",
        name="DraftKings Salary Refresh",
    )
    scheduler.add_job(
        refresh_ownership,
        "interval",
        seconds=SCHEDULE_INTERVALS["ownership"],
        id="ownership",
        name="Ownership Projections Refresh",
    )
    scheduler.add_job(
        refresh_depth_charts,
        "interval",
        seconds=SCHEDULE_INTERVALS["depth_charts"],
        id="depth_charts",
        name="Depth Charts Refresh",
    )

    # Fire initial fetch immediately (runs in background, doesn't block startup)
    scheduler.add_job(
        run_initial_fetch,
        "date",  # one-shot trigger
        id="initial_fetch",
        name="Initial Data Fetch",
    )

    scheduler.start()
    logger.info("Scheduler started with all jobs + initial fetch queued")


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    scheduler.shutdown(wait=False)
    logger.info("Scheduler shut down")
