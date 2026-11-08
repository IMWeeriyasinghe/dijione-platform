# DijiOne Local Development

Running every DijiOne service locally on **Windows or macOS**. See
`docs/platform/service-architecture.md` for what each service is and
`docs/setup.md` for the pre-split single-app setup this superseded.

Each machine has its own clone and restores its own dependencies. Never copy
`.venv` or `node_modules` between operating systems: they contain
platform-specific binaries.

## Prerequisites

- Node.js 20 (`.nvmrc`) and Python 3.12 (`.python-version`).
- One shared Python virtualenv at the repo root (`./.venv`) holding every
  backend service's requirements. Separate processes and ports are enough in
  development; separate virtualenvs are not needed.

| | Windows | macOS |
|---|---|---|
| Create the virtualenv | `py -3.12 -m venv .venv` | `python3.12 -m venv .venv` |
| Activate (optional) | `.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |
| Python executable | `.venv\Scripts\python.exe` | `.venv/bin/python` |

On macOS, call `python3.12` explicitly, because bare `python3` may be a
different version and bare `python` may not exist.

Install the requirements **from each service's directory**, because they use
relative `-e ../../packages/...` paths.

Windows (PowerShell, from the repo root):

```powershell
Get-ChildItem apps -Directory -Filter *-api | ForEach-Object {
  Push-Location $_.FullName
  ..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
  Pop-Location
}
```

macOS (from the repo root):

```bash
for s in apps/*-api; do
  (cd "$s" && ../../.venv/bin/python -m pip install -r requirements.txt)
done
```

### npm workspace

Run `npm ci` at the repo root. It installs exactly what `package-lock.json`
pins and links every workspace package under `node_modules/@dijione/*`. Use
`npm install` only when you intend to change dependencies.

`npm ci` deletes any existing `node_modules` first.

## Applications and ports

| Service | Port | Health check |
|---|---|---|
| `shell-web` | 3000 | `GET http://localhost:3000/` |
| `admin-web` | 3001 | `GET http://localhost:3001/admin` (its `basePath`) |
| `talent-web` | 3002 | `GET http://localhost:3002/talent-flow` (its `basePath`) |
| `birthday-web` | 3003 | `GET http://localhost:3003/birthday` (its `basePath`) |
| `onsite-web` | 3004 | `GET http://localhost:3004/onsite` (its `basePath`) |
| `atwork-web` | 3005 | `GET http://localhost:3005/atwork` (its `basePath`) |
| `birthday-supplier-web` | 3006 | `GET http://localhost:3006/` (own hostname in prod; not proxied through shell-web) |
| `talentflow-portal-web` | 3100 | `GET http://localhost:3100/` (external workspace; not proxied through shell-web) |
| `platform-api` | 8000 | `GET http://localhost:8000/health` |
| `admin-api` | 8001 | `GET http://localhost:8001/health` |
| `talent-api` | 8002 | `GET http://localhost:8002/health` |
| `birthday-api` | 8003 | `GET http://localhost:8003/health` |
| `spark-api` | 8004 | `GET http://localhost:8004/health` |
| `recruitment-api` | 8005 | `GET http://localhost:8005/health` (internal ingress only — no gateway route) |
| `people-api` | 8006 | `GET http://localhost:8006/health` (internal ingress only — no gateway route) |
| `commercial-api` | 8007 | `GET http://localhost:8007/health` (internal ingress only — skeleton) |
| `onsite-api` | 8008 | `GET http://localhost:8008/health` |
| `atwork-api` | 8009 | `GET http://localhost:8009/health` |

Always develop against `http://localhost:3000` — that's the gateway. The
zones are independently runnable on their own ports for isolated testing, but
a browser visiting them directly bypasses shell-web's common nav/auth chrome
and cross-zone links back to Home.

## Local mock settings

Services default to mock integrations and disabled outbound email, but a
service's `apps/<service>/.env` can override those defaults. Process
environment variables take priority over `.env`, so set these to guarantee
mock behaviour for a session:

| Variable | Value |
|---|---|
| `INTEGRATIONS_MODE` | `mock` |
| `EMAIL_SENDING_MODE` | `mock` |
| `MAIL_TRANSPORT` | `null` |

Windows (PowerShell):

```powershell
$env:INTEGRATIONS_MODE="mock"; $env:EMAIL_SENDING_MODE="mock"; $env:MAIL_TRANSPORT="null"
```

macOS:

```bash
export INTEGRATIONS_MODE=mock EMAIL_SENDING_MODE=mock MAIL_TRANSPORT=null
```

Real `.env` files are per-machine and never committed; start from each
service's `.env.example`.

## Databases and migrations

By default each database-backed service uses its own local SQLite file,
`apps/<service>/<name>.db`. `admin-api` and `spark-api` have no database. Each
machine's files are separate and are not synchronised through Git.

- Run `python -m alembic upgrade head` from a service's directory, using the
  virtualenv's Python, after pulling changes that touch its `alembic/` folder.
- Copy a `.db` file somewhere safe before migrating it if you care about its
  contents.
- `DATABASE_URL` overrides the default, and Alembic reads the same setting, so
  you can try a migration on a throwaway file first:

  ```bash
  # macOS, from apps/<service>; path is an example
  DATABASE_URL="sqlite:////tmp/dijione-try.db" ../../.venv/bin/python -m alembic upgrade head
  ```

  ```powershell
  # Windows, from apps\<service>; path is an example
  $env:DATABASE_URL="sqlite:///C:/Temp/dijione-try.db"
  ..\..\.venv\Scripts\python.exe -m alembic upgrade head
  Remove-Item Env:DATABASE_URL
  ```

- **`scripts/seed.py --reset` and `scripts/bootstrap-dev.sh` reset local
  data.** Only run them when you mean to discard it.
- Run tests with a throwaway `DATABASE_URL` if you want to leave existing
  `test_*.db` files untouched.

## One command

```bash
npm run dev:all
```

Runs `scripts/dev-all.js`, which spawns all sixteen processes (nine Python
services via the repo-root `.venv`, seven Next.js apps via their own workspace
`dev` script), tags every log line with a colored `[service-name]` prefix, and
shuts everything down together on Ctrl-C. No Docker required — this is plain
`child_process.spawn`, chosen as the lowest-complexity option that actually
works (CR §31).

- It looks for `.venv/Scripts/python.exe` on Windows and `.venv/bin/python` on
  macOS, so the virtualenv must exist at the repo root and be built on that
  operating system.
- It opens each service's **existing local database** and reads its `.env`. It
  does not run migrations.
- Set the mock variables above first.
- For a startup check that leaves local databases alone, also set
  `DATABASE_URL` to one throwaway SQLite file before running it. Every service
  then shares that file, so use this only to check startup, not to work.
- Stop it with Ctrl-C. If you kill only the parent process, Next.js servers can
  be left running; see Troubleshooting.

**Windows note**: the script deliberately does *not* pass `shell: true` to
the Python child processes — only to `npm` — since `shell: true` combined
with an absolute path containing spaces (a repo path like
`C:\Projects\My Team\...`) causes `cmd.exe` to mis-split the command and
fail with `'C:\Projects\My' is not recognized...`. If you hit that error
after modifying `scripts/dev-all.js`, this is almost certainly why.

## Seeding demo data

**This discards the data in the local databases it touches.** Seed
**platform-api first, then talent-api**.

Windows (PowerShell):

```powershell
cd apps\platform-api; ..\..\.venv\Scripts\python.exe scripts\seed.py --reset
cd ..\talent-api;   ..\..\.venv\Scripts\python.exe scripts\seed.py --reset
```

macOS:

```bash
cd apps/platform-api && ../../.venv/bin/python scripts/seed.py --reset
cd ../talent-api      && ../../.venv/bin/python scripts/seed.py --reset
```

`platform-api`'s seed script is the **permanent** owner of canonical Client
identity (Architecture Completion Plan §6.1): it creates the real,
DTC-verified client set (28 clients as of the DijiTalentFlow real-data
local validation, 2026-09-01 — see `apps/platform-api/app/core/
real_dev_clients.py`) with stable `public_id`s, and writes every
`UserModuleClientScope` / `UserModuleRole` row against the real
`client_ref` string, not a bare integer — client isolation does not depend
on seed-insertion order lining up across services. It creates only staff
personas (`ta-member`, `customer-success`, `ta-manager`,
`platform-admin`, `super-admin`, `ta-portfolio`) — there is **no**
client-login dev persona. External client/prospect access to DijiTalentFlow
is the real magic-link flow: a TA generates an access link (talent-web →
*Client Access Links*) for a real client organisation and opens it in
`talentflow-portal-web` (port 3100). See `docs/platform/data-ownership.md`
and the magic-link plan.

**`platform-api` must be running** (not just seeded) when you run
`talent-api`'s seed script — unlike its old demo-data version, the current
script has a **hard** dependency on platform-api: it fetches the real
client directory live via `GET /api/platform/internal/clients` and creates
only the matching local `Client` extension rows (`platform_client_id` +
`name`). It creates **no** demo TalentRequest/Candidate/Application/
Interview/Message/Document data — that was retired in the real-data
validation; real TalentFlow business data is populated by the recruitment
source-sync flow instead (`POST /api/recruitment/internal/sync`, see
`docs/platform/recruitment-source.md`). If platform-api isn't reachable,
the script raises immediately with a clear error rather than seeding a
partial/inconsistent local state.

## Running one service in isolation

Every backend service is a normal FastAPI app — from its own directory, using
`..\..\.venv\Scripts\python.exe` on Windows or `../../.venv/bin/python` on
macOS in place of `<python>`:

```bash
cd apps/talent-api
<python> -m uvicorn app.main:app --port 8002 --reload
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
cd apps/talent-api && <python> -m ruff check . && <python> -m pytest
cd apps/talent-web && npm run lint && npm run test && npm run build
```

## Troubleshooting

- **Port already in use.** A previous run's process may still be alive
  (uvicorn's `--reload` spawns a reloader *and* a worker process, and Next.js
  runs a separate server process). Find the real listener and stop it by PID.
  Windows: `netstat -ano | findstr :8002`, then `taskkill /F /PID <pid>`.
  macOS: `lsof -nP -iTCP:8002 -sTCP:LISTEN`, then `kill <pid>`.
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
