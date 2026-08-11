# DijiOne — Local Setup

## Prerequisites

- Node.js 20+ (repo built/tested with Node 22)
- Python 3.12 (a `py -3.12` launcher entry, or any `python3.12` on PATH)

## Backend (`apps/api`)

```bash
cd apps/api
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt

# Apply migrations
./.venv/Scripts/python.exe -m alembic upgrade head

# Seed realistic demo data (drops & recreates all tables first)
./.venv/Scripts/python.exe scripts/seed.py --reset

# Run the API
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload
```

The API is now at `http://localhost:8000` (`/docs` for Swagger UI,
`/api/health` for a liveness check).

### Backend tests / lint

```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
```

### Creating a new migration after model changes

```bash
./.venv/Scripts/python.exe -m alembic revision --autogenerate -m "describe the change"
./.venv/Scripts/python.exe -m alembic upgrade head
```

## Frontend (`apps/web`)

```bash
cd apps/web
npm install
```

Create `.env.local` (already present in this repo for local dev):

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_APP_ENV=development
```

```bash
npm run dev      # http://localhost:3000
npm run lint
npm run build     # production build + typecheck
```

## First run

1. Start the backend (seeded, on :8000).
2. Start the frontend (on :3000 — if that port is already used by another
   local process, Next.js automatically falls back to :3001, :3002, etc.
   and prints the actual URL; `API_CORS_ORIGINS` already allows :3000-:3002
   by default for exactly this reason, see `apps/api/app/core/config.py`).
3. Open the printed frontend URL — you'll land on the **Dev Identity Mode**
   persona switcher. Pick a persona (e.g. "Amal Perera" for the ABC
   Company client view, or "Madushanka Weeriyasinghe" for the Talent
   Acquisition workspace) to sign in.
4. Use the avatar menu (top right) → "Switch persona" to sign out and try
   a different role without restarting anything.

## Environment variables

See `.env.example` at the repository root for the full contract
(Entra ID, Lever, HubSpot, Azure Storage — none required for local dev;
see CLAUDE.md §58 / §74).
