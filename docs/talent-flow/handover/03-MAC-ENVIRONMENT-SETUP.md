# 03: Mac environment setup (MacBook Air M4, Apple Silicon)

[Start](00-START-HERE.md) · prev [02](02-APPLICATION-AND-ARCHITECTURE.md) · next [04 Git and migration plan](04-GIT-AND-MIGRATION-PLAN.md)

**Do not install anything until the owner approves the plan from the read-only check (Step 0).**

| Tool | Need |
|---|---|
| Git, Python 3.12, Node 20 with npm | **Mandatory** |
| Claude Code | **Mandatory** (the agent itself) |
| Homebrew | Recommended (installs the rest) |
| GitHub CLI `gh` | Optional, for PR and CI checks |
| Azure CLI + `containerapp` extension | Optional; only for read-only environment checks |
| Docker | **Not needed** for TalentFlow development. Optional, only to reproduce image builds (releases build in ACR) |
| PostgreSQL | **Not needed** locally (SQLite). CI covers PostgreSQL |

**Canonical Mac repository:** `/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform`. It was copied from Windows; do not clone it again.

**Requirements, taken from the repository:**
- **Python 3.12:** `.python-version`, and `deploy/Dockerfile.api` uses `python:3.12-slim`.
- **Node.js 20:** `.nvmrc`, and `deploy/Dockerfile.web` uses `node:20-slim`.
- **npm workspaces:** root `package.json` and `package-lock.json`.
- **APIs:** FastAPI with uvicorn. Local databases are SQLite; you do **not** need Docker or PostgreSQL for TalentFlow work.
- **Existing setup docs:** `docs/platform/local-development.md`. Its macOS section from #78 is on `feat/onsite-dashboard-v1`, **not** on `release/onsite-v1`. The release-line version uses Windows paths (`.venv/Scripts/...`); on macOS the equivalent is `.venv/bin/...`.

## Step 0: read-only readiness check (change nothing)

```bash
cd "/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform"
sw_vers; uname -m                       # expect arm64
git --version; git remote -v; git status -sb; git worktree list
git branch --show-current; git log --oneline -1
command -v brew node npm python3 python3.12 az docker claude gh
node -v 2>/dev/null; python3 --version; az version 2>/dev/null | head -5
ls -la .venv 2>/dev/null | head -3        # a Windows-built .venv will not work on macOS
ls apps/*/node_modules 2>/dev/null | head -1; ls node_modules | head -1
diskutil info "/Volumes/SD_APFS" | grep -E "File System|Owners"   # APFS? are permissions honoured?
```

**Copy artefacts that must be rebuilt on the Mac** (they are git-ignored, so deleting them is safe, but ask first):
- `.venv` built on Windows;
- every `node_modules`;
- `.next` build folders;
- `__pycache__`.

**`git worktree list` will show broken Windows paths** (`C:/Projects/...`). Do **not** run `git worktree prune` until the owner confirms the Windows worktrees are no longer needed. Pruning only removes metadata; the branches stay.

**Git settings to check:** `git config core.autocrlf` should be `input` or unset on macOS, and `git config core.fileMode`. If `git status` shows every file as modified after the copy, the cause is line endings or file modes, not real changes. Report it; do not "fix" it with a commit.

## Step 1: tools (after the owner approves)

```bash
# Homebrew: https://brew.sh (needs owner consent to install)
brew install git node@20 python@3.12 azure-cli gh
echo 'export PATH="/opt/homebrew/opt/node@20/bin:$PATH"' >> ~/.zshrc
# Claude Code: install per https://docs.claude.com/claude-code, then run `claude` and sign in
```

The **GitHub CLI** was not available on Windows. On the Mac, `gh auth login` makes PR and CI checks possible. Use HTTPS or SSH to match the remote: `https://github.com/IMWeeriyasinghe/dijione-platform.git`.

## Step 2: Python environment (shared repo-root venv)

```bash
python3.12 -m venv .venv
for a in platform-api talent-api recruitment-api admin-api; do ./.venv/bin/pip install -r apps/$a/requirements.txt; done
```

The requirements install `packages/auth-client-py` in editable mode (`-e ../../packages/auth-client-py`). pip resolves that path from the current directory, so if it fails, run the install from `apps/<api>/`.

## Step 3: Node packages

```bash
npm ci          # repo root, all workspaces (uses package-lock.json)
```

## Step 4: local configuration

- Copy `apps/<service>/.env.example` to `.env` for each service you run.
- Keep `APP_ENV=development`, `AUTH_MODE=dev`, `DEV_IDENTITY_MODE=true` (the defaults in `apps/platform-api/.env.example`), `INTEGRATIONS_MODE=mock`, and SQLite `DATABASE_URL`s.
- **Never put a hosted database URL, Lever key or Azure secret in a local `.env`.** Never copy them from Key Vault.

## Step 5: run locally

```bash
# seed: platform first (and it must be running), then talent (see local-development.md)
(cd apps/platform-api && ../../.venv/bin/python scripts/seed.py --reset)
(cd apps/platform-api && ../../.venv/bin/python -m uvicorn app.main:app --port 8000) &
(cd apps/talent-api   && ../../.venv/bin/python scripts/seed.py --reset)
npm run dev:all        # scripts/dev-all.js
```

`scripts/dev-all.js` is cross-platform (verified). On macOS it uses `.venv/bin/python` if that exists, and otherwise falls back to `python`. So create the venv first (Step 2). To run APIs by hand, the ports are: platform 8000, talent 8002, recruitment 8005, shell 3000, talent-web 3002, portal 3100. `dev:all` starts every module; you can run only the TalentFlow ones.

Open `http://localhost:3000`, then go to `/talent-flow`.

## Step 6: targeted tests (local only)

```bash
unset DATABASE_URL     # mandatory: test fixtures DROP tables of whatever DB this points to
cd apps/talent-api && ../../.venv/bin/python -m pytest -q tests -k "isolation or tenant or external or grant or scope or reconcile"
../../.venv/bin/ruff check .
cd ../platform-api && ../../.venv/bin/python -m pytest -q -k "auth or role or scope or entra"
cd ../talent-web && npm test && npm run lint
```

## Step 7: Azure CLI, read-only only

```bash
az login                      # interactive; the owner's account
az account show --query "{name:name,id:id}" -o table    # expect "Dijital Team IT Production"
az extension add --name containerapp --upgrade
```

**Allowed without asking:** read-only `show`/`list` commands (see [06](06-MAC-CLAUDE-BOOTSTRAP.md#read-only-verification-commands)).

**Needs approval first:** anything that starts a job execution, updates, suspends, resumes, imports or locks.

## Mac-specific risks

| Risk | Mitigation |
|---|---|
| External SD volume: case sensitivity, permissions, sleep or eject | Confirm APFS. Never run the repo from a FAT/exFAT card. Keep a pushed remote copy |
| Windows `.venv` and `node_modules` copied over | Recreate them (Steps 2–3) |
| CRLF line endings or file-mode changes after the copy | Check `git status` and the settings above before committing anything |
| Broken worktree metadata | Ignore, or prune only with approval |
| Scripts in the Windows session's temporary scratchpad (deployment runbooks and probes) | Reference copies are in [runbook/](runbook/README.md). The procedure is in [05](05-OPERATIONS-AND-OPEN-ITEMS.md). copied to [runbook/](runbook/README.md). Recreate them only when a deployment is approved |
| `node@20` not on `PATH` (it is keg-only) | Add it to `PATH` as in Step 1 |
