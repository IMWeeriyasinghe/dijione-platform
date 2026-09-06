#!/usr/bin/env bash
# DijiOne — Key Vault secret initialization (Amendment 3).
#
#   ./deploy/init-secrets.sh <env>
#
# Runs BETWEEN `foundation.bicep` and `main.bicep`:
#
#   foundation.bicep  ->  init-secrets.sh  ->  main.bicep
#   (KV empty)            (KV filled)          (Container Apps reference real values)
#
# Bicep never creates a secret VALUE (not even a placeholder). This script:
#   * generates the 3 trust anchors with `openssl rand` IF they are absent
#     (idempotent — an existing value is never overwritten);
#   * writes one `database-url-<domain>` per DB-owning service, built from the
#     foundation's PostgreSQL FQDN output + the admin password you enter now.
#
# A secret value is NEVER echoed and NEVER passed on a command line. Values go
# to `az keyvault secret set` through a private (umask 077) temp file that is
# shredded immediately — process substitution is not portable to Git Bash on
# Windows, where `az` (a Windows exe) cannot open an MSYS /proc/<pid>/fd path.
#
# The PostgreSQL admin password is taken from $PGADMIN_PASSWORD if set,
# otherwise prompted (hidden). It is never written to disk by this script.
#
# NOTHING here runs during planning. Phase 1+ runbook only.

set -euo pipefail
umask 077

ENV="${1:?usage: init-secrets.sh <env>}"
RG="rg-dijione-${ENV}"
KV="kv-dijione-${ENV}"
PG="psql-dijione-${ENV}"

DEPLOY_BIRTHDAY="${DEPLOY_BIRTHDAY:-true}"
DEPLOY_COMMERCIAL="${DEPLOY_COMMERCIAL:-false}"

# DB-owning services -> logical database (must match foundation.bicep).
DBS=(platform:platform_dev talent:talent_dev recruitment:recruitment_dev)
[ "$DEPLOY_BIRTHDAY" = "true" ]   && DBS+=(people:people_dev birthday:birthday_dev)
[ "$DEPLOY_COMMERCIAL" = "true" ] && DBS+=(commercial:commercial_dev)

echo "== resolving PostgreSQL FQDN for $PG =="
PG_FQDN="$(az postgres flexible-server show -g "$RG" -n "$PG" --query fullyQualifiedDomainName -o tsv)"
if [ -z "$PG_FQDN" ]; then
  echo "!! could not resolve $PG FQDN — has foundation.bicep been deployed to $RG?" >&2
  exit 1
fi
echo "   $PG_FQDN"

PG_PW="${PGADMIN_PASSWORD:-}"
if [ -z "$PG_PW" ]; then
  read -r -s -p "PostgreSQL admin password for $PG (input hidden): " PG_PW
  echo
fi
[ -n "$PG_PW" ] || { echo "!! empty password (set PGADMIN_PASSWORD or enter one)" >&2; exit 1; }

set_secret() {  # $1 = name, $2 = value  (value via private temp file, shredded)
  local tf
  tf="$(mktemp)"
  printf '%s' "$2" > "$tf"
  az keyvault secret set --vault-name "$KV" -n "$1" --file "$tf" -o none
  dd if=/dev/urandom of="$tf" bs=1 count="$(wc -c < "$tf")" conv=notrunc status=none 2>/dev/null || true
  rm -f "$tf"
}
secret_missing() {  # $1 = name -> 0 if absent or the old placeholder
  local v
  v="$(az keyvault secret show --vault-name "$KV" -n "$1" --query value -o tsv 2>/dev/null || true)"
  [ -z "$v" ] || [ "$v" = "set-me-via-deploy.sh" ]
}

echo "== trust anchors (generated only if absent) =="
for name in jwt-dev-secret internal-service-secret external-session-jwt-secret; do
  if secret_missing "$name"; then
    set_secret "$name" "$(openssl rand -hex 32)"
    echo "   $name  -> generated"
  else
    echo "   $name  -> already set (left unchanged)"
  fi
done

echo "== database URLs (rebuilt each run from the resolved FQDN) =="
for pair in "${DBS[@]}"; do
  domain="${pair%%:*}"; db="${pair##*:}"
  set_secret "database-url-${domain}" \
    "postgresql+psycopg://dijione:${PG_PW}@${PG_FQDN}:5432/${db}?sslmode=require"
  echo "   database-url-${domain}  -> set (${db})"
done

unset PG_PW
echo "== done. Every value lives only in $KV. Next: deploy/bicep/main.bicep =="
