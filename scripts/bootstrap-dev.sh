#!/usr/bin/env bash
# Deterministic first-boot for a fresh DijiOne environment.
#
#   1. apply migrations        (platform-api, then talent-api, then birthday-api)
#   2. seed the platform catalog + demo data   (roles / permissions / modules / personas)
#   3. seed talent-api demo data               (3 clients + requests / candidates / ...)
#
# A migrated-but-unseeded database is NOT a usable DijiOne environment — the
# role/permission/module catalog is populated by scripts/seed.py, not by any
# migration. Run this once per fresh database.
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
  echo "==> [$svc] alembic upgrade head"
  ( cd "$REPO_ROOT/apps/$svc" && "$PYTHON" -m alembic upgrade head )
}

seed() {
  local svc="$1"
  echo "==> [$svc] scripts/seed.py --reset"
  ( cd "$REPO_ROOT/apps/$svc" && "$PYTHON" scripts/seed.py --reset )
}

migrate platform-api
migrate talent-api
migrate birthday-api

# Order matters: talent-api's seed references platform personas / client ids
# by the fixed 1..9 / 1..3 integer convention (docs/platform/local-development.md).
seed platform-api
seed talent-api

echo "==> bootstrap complete"
