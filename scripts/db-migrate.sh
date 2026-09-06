#!/usr/bin/env bash
# MIGRATE — schema / catalog / reference only.
#
# Runs `alembic upgrade head` for every DB-owning service, each against its
# OWN alembic tree (apps/<svc>/alembic + apps/<svc>/alembic.ini). Nothing
# here seeds demo data or dev personas — that is `scripts/dev-identity-bootstrap.sh`
# (identity/RBAC prerequisites) and is deliberately separate from business
# data, which is NEVER seeded in a hosted environment (it originates from the
# controlled Recruitment Source / Lever GET-only sync + canonical
# organisation reconciliation — CLAUDE.md Data Ownership contract).
#
# This is the script hosted DEV / UAT / PROD run. In Azure it becomes ONE
# Container Apps Job PER DB-owning service, each using that service's own
# image (migration-execution ownership stays with the schema owner —
# deploy/bicep design "Migration Job"). Locally it is one checkout.
#
# Migration ownership is preserved: platform-api's migration
# (h8i9j0k1l2m3) seeds the platform-owned canonical Client master set per
# the data-ownership contract §2a — that is platform-owned *reference*
# master data, distinct from TalentFlow *business* records.
#
# DECIDED 2026-09-04 (Option A — final): the 28 real DTC-verified
# Client/Organisation rows are kept as platform-owned canonical master data
# and ship via this migration in hosted DEV/UAT/PROD. They are NOT fictional
# business records. Fictional TalentRequests / candidates / applications /
# interviews / messages / documents remain prohibited as seed data. See
# docs/platform/hosted-dev-data.md.
#
# Usage (each service's env — DATABASE_URL etc. — already set):
#   PYTHON=python ./scripts/db-migrate.sh
#   DEPLOY_BIRTHDAY=true DEPLOY_COMMERCIAL=true ./scripts/db-migrate.sh

set -euo pipefail

PYTHON="${PYTHON:-python}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_BIRTHDAY="${DEPLOY_BIRTHDAY:-true}"
DEPLOY_COMMERCIAL="${DEPLOY_COMMERCIAL:-false}"

# platform-api first: its catalog-seed migration (f6a7b8c9d0e1) makes the
# Admin Center usable, and its canonical Client set is what talent-api's
# extension rows reference.
SERVICES=(platform-api talent-api recruitment-api)
[ "$DEPLOY_BIRTHDAY" = "true" ] && SERVICES+=(people-api birthday-api)
[ "$DEPLOY_COMMERCIAL" = "true" ] && SERVICES+=(commercial-api)

for svc in "${SERVICES[@]}"; do
  if [ -d "$REPO_ROOT/apps/$svc/alembic" ]; then
    echo "==> [$svc] alembic upgrade head"
    ( cd "$REPO_ROOT/apps/$svc" && "$PYTHON" -m alembic upgrade head )
  else
    echo "==> [$svc] no alembic tree — skipping"
  fi
done

echo "==> migrate complete (schema + catalog/reference only; no business data)"
