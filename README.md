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

## Quick Start (Local)

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

## Deploy to Railway

This project is configured for deployment on [Railway](https://railway.app) as two services in one project.

### 1. Create a Railway project

Sign up at [railway.app](https://railway.app) with GitHub and create a new project from your repo.

### 2. Backend service

- Set **Root Directory** to `backend`
- Railway auto-detects Python and uses the included `Procfile`
- Go to **Networking** → **Generate Domain** to get a public URL
- Add these **Variables**:
  - `ALLOWED_ORIGINS` — your frontend Railway URL (e.g. `https://your-frontend.up.railway.app`)
  - `DATABASE_URL` *(optional)* — defaults to local SQLite; set to `sqlite+aiosqlite:////data/fantasy.db` if using a Railway Volume for persistent storage

### 3. Frontend service

- Click **New** → **GitHub Repo** → select the same repo
- Set **Root Directory** to `frontend`
- Go to **Networking** → **Generate Domain**
- Add these **Variables**:
  - `NEXT_PUBLIC_API_URL` — your backend Railway URL (e.g. `https://your-backend.up.railway.app`)

### 4. Persistent storage (recommended)

By default, Railway's filesystem resets on each deploy. To persist the database:

1. Go to the backend service → **New** → **Volume**
2. Set **Mount Path** to `/data`
3. Set the `DATABASE_URL` variable to `sqlite+aiosqlite:////data/fantasy.db`

### 5. Initial data sync

After both services deploy, click the **Sync Data** button in the UI header to trigger a full data fetch from all sources. This takes a few minutes.

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/projections` | Player projections (filter by position, salary, spot starts) |
| `GET /api/dvp` | Defense vs Position rankings |
| `GET /api/injuries` | Current injury report |
| `GET /api/lineups` | Today's starting lineups |
| `GET /api/spot-starts` | Spot start alerts sorted by value |
| `GET /api/players/{id}` | Detailed player breakdown |
| `GET\|POST /api/refresh` | Trigger a full data refresh from all sources |
| `GET /api/health` | Health check with database record counts |
| `WS /api/ws/projections` | Real-time updates |

## Environment Variables

| Variable | Service | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Frontend | Backend URL for API proxying (default: `http://localhost:8000`) |
| `ALLOWED_ORIGINS` | Backend | Comma-separated CORS origins (default: `http://localhost:3000`) |
| `DATABASE_URL` | Backend | SQLAlchemy database URL (default: local `fantasy.db`) |

## Data Refresh Schedule

- NBA stats: every 2 hours
- Injuries: every 15 minutes
- Starting lineups: every 5 minutes
- Ownership: every 30 minutes
- Depth charts: every 6 hours
