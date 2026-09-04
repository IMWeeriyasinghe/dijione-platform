#!/usr/bin/env bash
# DEV IDENTITY BOOTSTRAP — legitimate development identity / RBAC / persona
# prerequisites only.
#
# Creates the DijiOne staff dev-login personas (madushanka-ta,
# customer-success, ta-manager, platform-admin, super-admin) and their
# platform-role / module-role assignments, so `AUTH_MODE=dev` persona
# switching works for internal authorization testing behind the Easy Auth
# gate. It does NOT:
#   - seed the canonical Client / organisation master set (that is
#     platform-api's own migration — h8i9j0k1l2m3 — per the data-ownership
#     contract §2a);
#   - create the `ta-portfolio` portfolio-scope *demo* persona (it needs
#     client rows and only exists to demonstrate a feature, not to log in);
#   - create ANY TalentFlow business data (clients-as-business-records,
#     TalentRequests, candidates, applications, interviews, messages,
#     documents). Those originate from the controlled Recruitment Source
#     sync + canonical org reconciliation, never a seed.
#
# Run AFTER `scripts/db-migrate.sh`. Optional — a hosted environment may
# choose to create real users through the Admin Center instead. For LOCAL
# development use `scripts/bootstrap-dev.sh` (migrate + full demo seed).
#
# Usage (platform-api env already set; talent-api reachable if TALENT_EXT=1):
#   PYTHON=python ./scripts/dev-identity-bootstrap.sh
#   PYTHON=python TALENT_EXT=1 ./scripts/dev-identity-bootstrap.sh   # also mirror client extension rows

set -euo pipefail

PYTHON="${PYTHON:-python}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [platform-api] seed dev identity (personas + RBAC assignments only)"
( cd "$REPO_ROOT/apps/platform-api" && "$PYTHON" scripts/seed.py --identity-only )

if [ "${TALENT_EXT:-0}" = "1" ]; then
  echo "==> [talent-api] mirror Client extension rows from the canonical directory"
  echo "    (no business data — see apps/talent-api/scripts/seed.py docstring)"
  ( cd "$REPO_ROOT/apps/talent-api" && "$PYTHON" scripts/seed.py )
fi

echo "==> dev identity bootstrap complete"
