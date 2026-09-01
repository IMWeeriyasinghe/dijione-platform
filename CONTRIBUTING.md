# Contributing to DijiOne

This is a **private** repository. `docs/platform/local-development.md` is the
authoritative, detailed setup guide — this file is the short version plus the
rules CI enforces.

## Prerequisites

| Tool | Version | Pin |
|---|---|---|
| Node.js | 20.x | `.nvmrc` |
| Python | 3.12 | `.python-version` |
| npm | bundled with Node 20 | — |

## First-time setup

```bash
# 1. Frontend workspaces + shared TS packages
npm install

# 2. Shared Python virtualenv at the repo root
python -m venv .venv
# Windows:  . .venv/Scripts/activate     macOS/Linux:  . .venv/bin/activate

# 3. Backend dependencies (installs the shared auth client in editable mode too)
for s in platform-api admin-api talent-api birthday-api spark-api; do
  pip install -r "apps/$s/requirements.txt"
done

# 4. Per-service environment files (safe placeholders — see docs/platform/environment.md)
for s in platform-api admin-api talent-api birthday-api spark-api; do
  cp "apps/$s/.env.example" "apps/$s/.env"
done

# 5. Databases (platform first — seed order matters)
(cd apps/platform-api && alembic upgrade head && python scripts/seed.py --reset)
(cd apps/talent-api   && alembic upgrade head && python scripts/seed.py --reset)
(cd apps/birthday-api && alembic upgrade head)

# 6. Run everything (5 web + 5 API processes)
npm run dev:all
```

Open http://localhost:3000 and pick a persona in the Dev Identity switcher.

## Secret-scan pre-commit hook (required)

```bash
pip install pre-commit
pre-commit install
```

This runs `gitleaks` on every commit. Real credentials must **only** ever live in
an untracked `apps/<service>/.env` file — never in tracked files, commit
messages, test fixtures, or docs.

## Branch & PR workflow

- `main` is intended to be protected via GitHub branch protection (required
  status checks for every CI job/matrix leg, `enforce_admins`, no
  force-push, no direct pushes) — but this repo is currently on GitHub
  Free as a private repo, which does not support branch protection or
  rulesets (`gh api .../branches/main/protection` returns 403 "Upgrade to
  GitHub Pro or make this repository public"). Until that's resolved,
  there is **no GitHub-side enforcement on `main`** — the Engineering
  Gatekeeper's own verification is the only safety layer. See
  `docs/platform/engineering-gatekeeper.md` §4 for the target
  configuration and current status.
- Branch names: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- Commit messages follow **Conventional Commits**, scoped by area:
  `feat(talent): …`, `fix(birthday-api): …`, `chore(repo): …`, `docs(platform): …`.
- Keep commits small enough to review.
- PRs are verified and merged by the **Engineering Gatekeeper**, not by the
  PR author. The Gatekeeper independently re-checks CI, architecture,
  security, and migration safety before merging — a green check alone is
  not sufficient. See `docs/platform/engineering-gatekeeper.md` for the
  full contract, including the current rollout mode (shadow vs. full
  auto-merge) and the human-escalation triggers that pause it for your
  review instead of merging automatically.

## Quality gates (run before pushing — CI runs the same)

**Frontend** (per app, or `--workspaces`):

```bash
npm -w apps/<app> run lint
npm -w apps/<app> run build
```

**Backend** (from the service directory):

```bash
cd apps/<service>
ruff check .
pytest -q
```

**Migrations** (for `platform-api`, `talent-api`, `birthday-api`):

```bash
cd apps/<service> && alembic upgrade head
```

## Environment-variable rule

Any field added to an `app/core/config.py` `Settings` class **must** be mirrored,
with a safe placeholder or empty value, in that service's `.env.example` **in the
same PR**. The PR template has a checkbox for this. Full contract:
`docs/platform/environment.md`.

## What never gets committed

- `apps/*/.env` (real secrets) — only `*.env.example` is tracked
- `apps/*/*.db`, `*.sqlite*` — local data, may contain synced live data
- `node_modules/`, `.venv/`, `.next/`, `.turbo/`, `*.tsbuildinfo`, caches
- Key material: `*.pem`, `*.key`, `*.pfx`, `*.p12`, `serviceAccount*.json`, `secrets.json`
