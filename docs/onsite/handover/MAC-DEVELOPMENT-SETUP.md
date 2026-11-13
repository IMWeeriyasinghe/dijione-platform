# macOS development setup

Canonical paths (external APFS SSD):

| Repo | Mac path |
|---|---|
| DijiOne | `/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform` |
| DijiOnsite-Agent (recommended, mirrors the Windows layout) | `/Volumes/SD_APFS/Diji Projects/DijiOnsiteAgent Project/DijiOnsiteAgent` |

```bash
# Agent repo (only if not already cloned)
mkdir -p "/Volumes/SD_APFS/Diji Projects/DijiOnsiteAgent Project"
cd "/Volumes/SD_APFS/Diji Projects/DijiOnsiteAgent Project"
git clone https://github.com/IMWeeriyasinghe/DijiOnsite-Agent.git DijiOnsiteAgent
```
Paths contain spaces — always quote them. Keep the SSD mounted while tools run; if the volume is
case-sensitive APFS, verify imports still resolve (Windows/default macOS are case-insensitive) — **requires
validation**.

## DijiOne toolchain (from the repo)
| Tool | Required | Source |
|---|---|---|
| Node.js | **20** (`.nvmrc`); the Windows PC actually ran 22.21.1 successfully — treat 20 as the pin | `nvm install && nvm use` |
| npm workspaces | root `package-lock.json` | `npm ci` at repo root |
| Python | **3.12** (`.python-version`) | `brew install python@3.12` |
| One shared venv | repo-root `.venv` | see `docs/platform/local-development.md` (Windows + macOS sections) |
| Azure CLI | for read-only inventory | `brew install azure-cli` |
| go-sqlcmd (optional) | authoritative DB reads | `brew install sqlcmd` |
| Docker | not needed for tests (SQLite + mocks); only to build images locally | optional |

Bootstrap (exact commands follow `docs/platform/local-development.md`):
```bash
cd "/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform"
python3.12 -m venv .venv
for s in apps/*-api; do (cd "$s" && ../../.venv/bin/python -m pip install -r requirements.txt); done
# each requirements.txt pulls the shared client editable (-e ../../packages/auth-client-py) plus pytest/ruff
npm ci
```
`pyodbc` is in onsite-api requirements; on macOS it needs `brew install unixodbc` to install. The ODBC
driver itself is only needed for live Azure SQL (not for tests, which use the mock source) — **requires validation**.

## Safe validation commands (no network, no Azure)
```bash
(cd apps/onsite-api  && ../../.venv/bin/python -m pytest -q)          # expect 129 passed
(cd apps/onsite-api  && ../../.venv/bin/python -m ruff check app tests)
(cd apps/people-api  && ../../.venv/bin/python -m pytest -q)          # expect 35 passed
(cd packages/auth-client-py && ../../.venv/bin/python -m pytest -q)   # expect 19 passed
(cd apps/onsite-web  && npx vitest run && npx tsc --noEmit && npx eslint src)   # expect 68 passed
(cd apps/onsite-web  && npx next build)
node scripts/check-module-independence.js
```
Local full stack: `npm run dev:all` (mock modes; `docs/platform/local-development.md`). On-site in mock mode uses
`INTEGRATIONS_MODE=mock` with SQLite; dev sign-in via platform-api dev login.

## DijiOnsite-Agent on macOS
| Part | macOS? |
|---|---|
| `src/DijiOnsiteAgent.Core`, `src/DijiOnsiteAgent.Contracts`, `services/DijiOnsiteAttendance.Ingestion` (`net10.0`) | build + edit: yes |
| `tests/DijiOnsiteAgent.Core.Tests` (66), `tests/DijiOnsiteAttendance.Ingestion.Tests` (10) | expected to run — **requires validation** (DPAPI-dependent tests, if any, are Windows-only: `SecretProtector` throws on non-Windows) |
| `src/DijiOnsiteAgent` (WPF, `net10.0-windows`), service install, installer (Inno Setup), DPAPI | **Windows only** |
| `tests/DijiOnsiteAgent.IntegrationTests` (13) | need the local dev ZKBio PostgreSQL replica (`dev/scripts/replica.ps1`, Windows); not on Mac |
| Production PC operations | Windows PC only |
| Azure attendance infra (`deploy/azure/attendance/*.ps1`) | PowerShell scripts; `pwsh` on Mac possible but **requires validation**; production changes need approval |

.NET SDK: `global.json` pins `10.0.100` (rollForward latestFeature); install the .NET 10 SDK
(`brew install --cask dotnet-sdk` or Microsoft installer). Run per project, not the whole `.slnx`, on Mac:
```bash
dotnet test tests/DijiOnsiteAgent.Core.Tests
dotnet test tests/DijiOnsiteAttendance.Ingestion.Tests
```
Never copy `bin/`, `obj/`, `.venv`, `node_modules`, `.local/`, `publish/`, `artifacts/` between machines.
