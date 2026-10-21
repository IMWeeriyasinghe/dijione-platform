#!/usr/bin/env bash
# DijiOne artifact promotion (Amendment 4) — build once, promote the EXACT
# immutable digest. The production image is NEVER rebuilt.
#
#   ./deploy/promote.sh <fromEnv> <toEnv> <gitsha>
#
#   promote.sh dev uat <gitsha>
#     -> same registry (crdijionenonprod), same digests. Just deploy
#        main.uat.bicepparam pointing at those digests. Nothing is copied.
#
#   promote.sh uat prod <gitsha>
#     -> `az acr import` each digest from crdijionenonprod into crdijioneprod
#        (a manifest copy — the digest is preserved, no rebuild), VERIFY the
#        imported digest equals the source, then deploy main.prod.bicepparam.
#
# The digests promoted are read from the <fromEnv> workloads deployment, so
# what ships downstream is provably the artifact that passed upstream.
#
# NOTHING here runs during planning. Phase 1+ runbook only.

set -euo pipefail

FROM="${1:?usage: promote.sh <fromEnv> <toEnv> <gitsha>}"
TO="${2:?usage: promote.sh <fromEnv> <toEnv> <gitsha>}"
GITSHA="${3:?usage: promote.sh <fromEnv> <toEnv> <gitsha>}"
FROM_RG="rg-dijione-${FROM}"
TO_RG="rg-dijione-${TO}"
BICEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/bicep" && pwd)"

NONPROD_ACR="crdijionenonprod"
PROD_ACR="crdijioneprod"

echo "== read the digests that passed $FROM =="
DIGESTS_JSON="$(az deployment group show -g "$FROM_RG" -n "dijione-workloads-${GITSHA}" \
  --query 'properties.parameters.imageDigests.value' -o json)"
[ -n "$DIGESTS_JSON" ] && [ "$DIGESTS_JSON" != "null" ] || {
  echo "!! no imageDigests recorded on dijione-workloads-${GITSHA} in $FROM_RG" >&2; exit 1; }
echo "$DIGESTS_JSON" | python -c 'import sys,json; [print(f"   {k}  {v}") for k,v in json.load(sys.stdin).items()]'

if [ "$TO" = "prod" ]; then
  echo "== import each digest crdijionenonprod -> crdijioneprod (manifest copy, no rebuild) =="
  # Cross-subscription: add  --username / --password  or run as an identity with
  # AcrPull on the source and AcrPush on the target.
  while IFS=$'\t' read -r svc digest; do
    [ -n "$svc" ] || continue
    # --image/-t requires a repo:tag target — this az CLI rejects a
    # "repo@digest" target string outright (InvalidImportImageParameter).
    # --repository is the manifest-only-copy form: it preserves the source
    # digest exactly with no tag, which is what a digest-pinned deployment
    # needs anyway (verified below).
    az acr import -n "$PROD_ACR" \
      --source "${NONPROD_ACR}.azurecr.io/dijione/${svc}@${digest}" \
      --repository "dijione/${svc}" -o none
    got="$(az acr repository show -n "$PROD_ACR" --image "dijione/${svc}@${digest}" --query digest -o tsv)"
    if [ "$got" != "$digest" ]; then
      echo "!! digest mismatch for $svc: expected $digest got $got" >&2
      exit 1
    fi
    echo "   $svc  verified $got"
  done < <(echo "$DIGESTS_JSON" | python -c 'import sys,json; [print(f"{k}\t{v}") for k,v in json.load(sys.stdin).items()]')
fi

echo "== unpark $TO PostgreSQL (idempotent) =="
az postgres flexible-server start -g "$TO_RG" -n "psql-dijione-${TO}" -o none 2>/dev/null || true

echo "== assert $TO Key Vault secrets are set =="
mapfile -t EXPECTED < <(az deployment group show -g "$TO_RG" --query \
  "properties.outputs.expectedSecretNames.value" -o tsv 2>/dev/null \
  -n "$(az deployment group list -g "$TO_RG" --query "[?contains(name,'foundation')]|[0].name" -o tsv)" | tr '\t' '\n' || true)
for name in "${EXPECTED[@]}"; do
  [ -n "$name" ] || continue
  v="$(az keyvault secret show --vault-name "kv-dijione-${TO}" -n "$name" --query value -o tsv 2>/dev/null || echo "")"
  if [ -z "$v" ] || [ "$v" = "set-me-via-deploy.sh" ]; then
    echo "!! $TO Key Vault secret '$name' unset. Run: deploy/init-secrets.sh ${TO}" >&2
    exit 1
  fi
done

echo "== deploy $TO workloads with the promoted digests =="
az deployment group create -g "$TO_RG" -n "dijione-workloads-${GITSHA}" \
  -f "$BICEP_DIR/main.bicep" -p "$BICEP_DIR/main.${TO}.bicepparam" \
  -p imageDigests="$DIGESTS_JSON" \
  -o none

echo "== run $TO migrate jobs =="
MIGRATE_TARGETS=(platform-api talent-api recruitment-api)
{ [ "${DEPLOY_BIRTHDAY:-true}" = "true" ] || [ "${DEPLOY_ONSITE:-false}" = "true" ]; } && MIGRATE_TARGETS+=(people-api)
[ "${DEPLOY_BIRTHDAY:-true}" = "true" ] && MIGRATE_TARGETS+=(birthday-api)
[ "${DEPLOY_ONSITE:-false}" = "true" ] && MIGRATE_TARGETS+=(onsite-api)
for t in "${MIGRATE_TARGETS[@]}"; do
  echo "  -> migrate-$t"
  az containerapp job start -g "$TO_RG" -n "migrate-$t" -o none
done

echo "== $TO promotion complete — same digests as $FROM =="
