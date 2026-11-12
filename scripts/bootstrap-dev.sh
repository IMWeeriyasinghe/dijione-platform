#!/usr/bin/env bash
# ============================================================================
# LOCAL DEVELOPMENT ONLY. Do NOT run this in a hosted environment.
#
# It seeds the full local demo dataset, including the `ta-portfolio` demo
# persona and its 2-client portfolio scope. Hosted DEV / UAT / PROD use the
# split scripts instead:
#
#   scripts/db-migrate.sh              schema + catalog/reference only
#   scripts/dev-identity-bootstrap.sh  staff dev personas + RBAC only (optional)
#
# Hosted TalentFlow BUSINESS data (clients-as-records, TalentRequests,
# candidates, applications, interviews, messages, documents) is NEVER
# seeded — it originates from the controlled Recruitment Source / Lever
# GET-only sync + canonical organisation reconciliation. The canonical
# Client MASTER set is platform-owned reference data seeded by
# platform-api's own migration (h8i9j0k1l2m3). See
# docs/platform/hosted-dev-data.md.
# ============================================================================
#
# Deterministic first-boot for a fresh LOCAL DijiOne database:
#
#   1. apply migrations for every DB-owning service
#   2. seed platform-api's dev personas + module-role/client-scope
#      assignments (the RBAC catalog + module registry are also migration-
#      seeded by f6a7b8c9d0e1, so step 1 alone already makes the Admin
#      Center usable; this adds the demo personas on top)
#   3. mirror talent-api's Client extension rows from the canonical directory
#      (no fictional TalentRequest/Candidate/Application/... — those were
#      retired; real business data comes from the recruitment sync flow)
#
# Only the source-domain services (recruitment-api, people-api,
# commercial-api) are migrated if this environment deploys them; they have
# no seed script — their migrations leave them correctly empty until a sync
# run populates them.
#
# Usage (from the repo root, with each service's env already set —
#   DATABASE_URL, PLATFORM_JWT_SECRET, INTERNAL_SERVICE_SECRET, INTEGRATIONS_MODE=mock, ...):
#
#   PYTHON=python ./scripts/bootstrap-dev.sh

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
