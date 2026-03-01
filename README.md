# Fantasy Basketball Predictor

DraftKings fantasy basketball projection tool with real-time lineup tracking, DvP analysis, spot start detection, and ownership projections.

## Features

- **Defense vs Position (DvP)**: Ranks matchups by position using last 10 games of data
- **Starting Lineup Monitoring**: Scrapes Rotowire for confirmed lineups every 5 minutes
- **Spot Start Detection**: Identifies bench players elevated to starter roles, analyzes their historical spot start performance, and flags cheap/min-price value plays
- **Injury Tracking**: Real-time injury report scraping with impact analysis
- **Ownership Projections**: DraftKings projected ownership from RotoGrinders
- **Real-Time Updates**: WebSocket-powered live updates for lineups, injuries, and projections

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, APScheduler, nba_api, BeautifulSoup
- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **Database**: SQLite
- **Real-time**: WebSockets

## Quick Start

### Backend

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 to view the dashboard. The frontend proxies API requests to the backend on port 8000.

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/projections` | Player projections (filter by position, salary, spot starts) |
| `GET /api/dvp` | Defense vs Position rankings |
| `GET /api/injuries` | Current injury report |
| `GET /api/lineups` | Today's starting lineups |
| `GET /api/spot-starts` | Spot start alerts sorted by value |
| `GET /api/players/{id}` | Detailed player breakdown |
| `WS /api/ws/projections` | Real-time updates |

## Data Refresh Schedule

- NBA stats: every 2 hours
- Injuries: every 15 minutes
- Starting lineups: every 5 minutes
- Ownership: every 30 minutes
- Depth charts: every 6 hours
