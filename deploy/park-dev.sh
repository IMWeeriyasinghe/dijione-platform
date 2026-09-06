#!/usr/bin/env bash
# DijiOne DEV cost park (Amendment 8). Stops the PostgreSQL Flexible Server so
# only storage (~$4-5/mo) is billed. Every Container App is already
# minReplicas=0 and idles at $0 — nothing to do for them.
#
# A stopped Flexible Server auto-resumes after 7 days; re-run this to keep it
# parked. `deploy/wake-dev.sh` brings it back.
#
#   ./deploy/park-dev.sh          # ENV defaults to dev
set -euo pipefail
ENV="${1:-dev}"
az postgres flexible-server stop -g "rg-dijione-${ENV}" -n "psql-dijione-${ENV}" -o none
echo "psql-dijione-${ENV} stopped. Storage-only billing. wake-dev.sh to resume."
