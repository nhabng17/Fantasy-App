from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR / 'fantasy.db'}"

DK_SCORING = {
    "pts": 1.0,
    "three_pm": 0.5,
    "reb": 1.25,
    "ast": 1.5,
    "stl": 2.0,
    "blk": 2.0,
    "tov": -0.5,
    "dd_bonus": 1.5,
    "td_bonus": 3.0,
}

POSITIONS = ["PG", "SG", "SF", "PF", "C"]

MIN_SALARY = 3500
MAX_VALUE_SALARY = 4500

USUAL_STARTER_THRESHOLD = 7  # started 7+ of last 10 games

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

SCHEDULE_INTERVALS = {
    "nba_stats": 7200,       # 2 hours
    "injuries": 900,         # 15 minutes
    "starting_lineups": 300, # 5 minutes
    "ownership": 1800,       # 30 minutes
    "depth_charts": 21600,   # 6 hours
}
