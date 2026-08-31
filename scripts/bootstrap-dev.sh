#!/usr/bin/env bash
# Deterministic first-boot for a fresh DijiOne environment.
#
#   1. apply migrations for every DB-owning service
#   2. seed platform-api's demo data (dev personas + module-role/client-scope
#      assignments) — the role/permission/module_registry catalog itself is
#      now seeded by platform-api's own f6a7b8c9d0e1 migration (Architecture
#      Completion Plan Wave G), so step 1 alone already makes the Admin
#      Center usable; this step adds the *demo* dev personas on top
#   3. seed talent-api demo data (3 clients + requests / candidates / ...)
#
# Only migrate/seed the source-domain services (recruitment-api, people-api,
# commercial-api) if this environment deploys them — they have no demo-data
# seed script of their own (source domains hold synced provider data, not
# hand-authored fixtures); their migrations alone leave them correctly empty
# until a sync run populates them.
#
# Usage (from the repo root, with each service's env already set —
#   DATABASE_URL, JWT_DEV_SECRET, INTERNAL_SERVICE_SECRET, INTEGRATIONS_MODE=mock, ...):
#
#   PYTHON=python ./scripts/bootstrap-dev.sh
#
# In Azure this is invoked as a Container Apps one-off job that shares the
# API images and their env — see deploy/README.md.

set -euo pipefail

PYTHON="${PYTHON:-python}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

migrate() {
  local svc="$1"
  if [ -d "$REPO_ROOT/apps/$svc" ]; then
    echo "==> [$svc] alembic upgrade head"
    ( cd "$REPO_ROOT/apps/$svc" && "$PYTHON" -m alembic upgrade head )
  fi
}

seed() {
  local svc="$1"
  echo "==> [$svc] scripts/seed.py --reset"
  ( cd "$REPO_ROOT/apps/$svc" && "$PYTHON" scripts/seed.py --reset )
}

migrate platform-api
migrate talent-api
migrate recruitment-api
migrate people-api
migrate commercial-api
migrate birthday-api

# Order matters: talent-api's seed references platform-api's dev-persona user
# ids by a fixed 1..9 convention (docs/platform/local-development.md) — run
# platform-api's seed first. Client identity itself no longer depends on
# insertion order (platform-owned canonical Client since Wave A).
seed platform-api
seed talent-api

echo "==> bootstrap complete"
