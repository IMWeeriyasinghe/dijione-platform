# DijiOne Local Development (Phase 2.5)

Running all eight DijiOne services locally. See
`docs/platform/service-architecture.md` for what each service is and
`docs/setup.md` for the pre-split single-app setup this superseded.

## Prerequisites

- Node.js 20+, Python 3.12 (matches `.venv` if you reuse the one already
  in the repo root).
- One shared Python virtualenv at the repo root (`./.venv`) with every
  backend service's `requirements.txt` installed into it — there's no need
  for five separate venvs in dev, only separate processes/ports:

  ```bash
  python -m venv .venv
  ./.venv/Scripts/pip install -r apps/platform-api/requirements.txt
  ./.venv/Scripts/pip install -r apps/admin-api/requirements.txt
  ./.venv/Scripts/pip install -r apps/talent-api/requirements.txt
  ./.venv/Scripts/pip install -r apps/birthday-api/requirements.txt
  ./.venv/Scripts/pip install -r apps/spark-api/requirements.txt
  ./.venv/Scripts/pip install -r apps/recruitment-api/requirements.txt
  ```

  (`requirements.txt` for `admin-api`, `talent-api`, `birthday-api`,
  `spark-api` each include `-e ../../packages/auth-client-py`, so one of
  those installs also makes `packages/auth-client-py` importable.)

- `npm install` at the repo root — this is a real npm workspace now
  (`apps/shell-web`, `apps/admin-web`, `apps/talent-web`,
  `packages/design-system`, `packages/auth-client-ts`,
  `packages/contracts`), so one install wires up every workspace package
  as a symlink under `node_modules/@dijione/*`.

## Ports

| Service | Port | Health check |
|---|---|---|
| `shell-web` | 3000 | `GET http://localhost:3000/` |
| `admin-web` | 3001 | `GET http://localhost:3001/admin` (its `basePath`) |
| `talent-web` | 3002 | `GET http://localhost:3002/talent-flow` (its `basePath`) |
| `birthday-web` | 3003 | `GET http://localhost:3003/birthday` (its `basePath`) |
| `platform-api` | 8000 | `GET http://localhost:8000/health` |
| `admin-api` | 8001 | `GET http://localhost:8001/health` |
| `talent-api` | 8002 | `GET http://localhost:8002/health` |
| `birthday-api` | 8003 | `GET http://localhost:8003/health` |
| `spark-api` | 8004 | `GET http://localhost:8004/health` |
| `recruitment-api` | 8005 | `GET http://localhost:8005/health` |

Always develop against `http://localhost:3000` — that's the gateway.
`admin-web`/`talent-web` are independently runnable on their own ports for
isolated testing, but a browser visiting them directly bypasses shell-web's
common nav/auth chrome and cross-zone links back to Home.

## One command

```bash
npm run dev:all
```

Runs `scripts/dev-all.js`, which spawns all nine processes (Python
services via the repo-root `.venv`, Next.js apps via their own workspace
`dev` script), tags every log line with a colored `[service-name]` prefix,
and shuts everything down together on Ctrl-C. No Docker required — this is
plain `child_process.spawn`, chosen as the lowest-complexity option that
actually works (CR §31).

**Windows note**: the script deliberately does *not* pass `shell: true` to
the Python child processes — only to `npm` — since `shell: true` combined
with an absolute path containing spaces (a repo path like
`C:\Projects\My Team\...`) causes `cmd.exe` to mis-split the command and
fail with `'C:\Projects\My' is not recognized...`. If you hit that error
after modifying `scripts/dev-all.js`, this is almost certainly why.

## Seeding demo data

Seed **platform-api first, then talent-api** — talent-api's seed data
references user ids and client-scope rows platform-api's seed created, by
plain integer convention (there's no foreign key across the database
boundary to enforce order, so the order itself matters):

```bash
cd apps/platform-api && ../../.venv/Scripts/python scripts/seed.py --reset
cd ../talent-api      && ../../.venv/Scripts/python scripts/seed.py --reset
```

The convention both scripts rely on: platform-api's dev personas get ids
1–9 in a fixed order (`madushanka`=1, `cs_user`=2, `ta_manager`=3,
`platform_admin`=4, `super_admin`=5, `abc_client`=6, `xyz_client`=7,
`nova_client`=8, `ta_portfolio`=9); talent-api's clients get ids 1–3 in
order (ABC Company, XYZ Company, Nova Solutions). Both scripts' docstrings
spell this out — if you add a new persona or client, keep the insertion
order stable or update both scripts together.

Talent-api's seed script drives real service calls (creating requests,
applications, interviews, etc.), which means it also attempts real
audit-event/notification writes to `platform-api`. If `platform-api` isn't
running yet when you seed `talent-api`, seeding still completes (those
writes are best-effort — see `docs/platform/failure-isolation.md`) but
prints a series of "non-fatal" timeout warnings and takes noticeably
longer. Start `platform-api` first to avoid this.

## Running one service in isolation

Every backend service is a normal FastAPI app — from its own directory:

```bash
cd apps/talent-api
../../.venv/Scripts/python -m uvicorn app.main:app --port 8002 --reload
```

Every frontend app is a normal Next.js app:

```bash
cd apps/talent-web
npm run dev
```

Each service's tests run from its own directory with no other service
required to be running (backend services mock/stub their upstream
dependencies in tests — see e.g. `apps/talent-api/tests/conftest.py`'s
`platform_calls` fixture, `apps/admin-api/tests/conftest.py`'s stub
platform/talent apps):

```bash
cd apps/talent-api && ../../.venv/Scripts/python -m pytest
cd apps/talent-web && npm run build && npx eslint .
```

## Troubleshooting

- **Port already in use.** `npm run dev:all` doesn't reuse ports across
  restarts cleanly on Windows if a previous run's process is still alive
  (uvicorn's `--reload` spawns a reloader *and* a worker process — killing
  one doesn't always kill the other). Find the real listener and kill it
  by PID: `netstat -ano | findstr :8002` then `taskkill /F /PID <pid>`.
- **A module card is stuck on "Checking…" forever.** That query has a 4s
  timeout — if it's still spinning past that, the browser tab may be
  throttled (backgrounded) rather than the service being slow; React
  Query's timers pause in background tabs.
- **First navigation into `/admin`, `/talent-flow`, or `/birthday` (or any
  route inside them, especially dynamic routes like `/birthday/orders/42`)
  is slow — sometimes several seconds, occasionally much longer on a
  loaded dev machine.** Expected in dev — Next.js/Turbopack compiles each
  route on first request in that zone's process; subsequent loads of the
  same route are 10-90x faster. Cross-zone navigation is always a full
  browser page load (plain `<a>`, not `next/link` — see
  `docs/platform/service-contracts.md`), so this compile tax is paid once
  per zone process per dev session, not once globally. Confirmed
  dev-mode-only: a production build (`next build && next start`) shows no
  cold/warm gap at all. Don't mistake this for a gateway/proxy problem —
  see `docs/platform/performance-investigation.md` for the full
  measurement writeup.
