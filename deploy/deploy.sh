#!/usr/bin/env bash
# DijiOne deploy — operator-run, one environment at a time. No CI/CD yet.
#
#   ./deploy/deploy.sh <env> <gitsha>
#
# Lifecycle (Amendments 3 + 4):
#
#   1. FOUNDATION   foundation.<env>.bicepparam  -> VNet/DNS, Log Analytics,
#                   Key Vault (EMPTY), PostgreSQL, Container Apps Environment
#   2. BUILD ONCE   az acr build each image into crdijionenonprod as :<gitsha>,
#                   record the immutable sha256 digest of each
#   3. SECRETS      assert every expected Key Vault secret has a real value
#                   (deploy/init-secrets.sh writes them — run it before step 4)
#   4. WORKLOADS    main.<env>.bicepparam -p imageDigests=<recorded>
#   5. PER-SVC ENV  internal http://<name> URLs + modes (kept out of Bicep)
#   6. MIGRATE      per-service migrate-<svc> jobs (schema owner runs its own)
#   7. SMOKE        /health/deep on each backend
#
# For PROD the image is NOT built here — it is imported from the non-prod
# registry by deploy/promote.sh (build once / promote the exact digest).
#
# Requires: az login; rg-dijione-<env> and rg-dijione-shared already created;
# for a first bring-up, deploy/init-secrets.sh already run.
#
# NOTHING here runs during planning. Phase 1+ runbook only.

set -euo pipefail

ENV="${1:?usage: deploy.sh <env> <gitsha>}"
GITSHA="${2:?usage: deploy.sh <env> <gitsha>}"
RG="rg-dijione-${ENV}"
BICEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/bicep" && pwd)"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Non-prod registry is shared by DEV + UAT and lives in rg-dijione-shared.
NONPROD_ACR="crdijionenonprod"
if [ "$ENV" = "prod" ]; then
  echo "!! deploy.sh does not build for prod — use: deploy/promote.sh uat prod" >&2
  exit 1
fi
ACR="$NONPROD_ACR"

DEPLOY_BIRTHDAY="${DEPLOY_BIRTHDAY:-true}"
DEPLOY_COMMERCIAL="${DEPLOY_COMMERCIAL:-false}"

API_SERVICES=(platform-api admin-api talent-api recruitment-api)
WEB_APPS=(shell-web admin-web talent-web talentflow-portal-web)
MIGRATE_TARGETS=(platform-api talent-api recruitment-api)
if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  API_SERVICES+=(people-api birthday-api)
  WEB_APPS+=(birthday-web birthday-supplier-web)
  MIGRATE_TARGETS+=(people-api birthday-api)
fi
if [ "$DEPLOY_COMMERCIAL" = "true" ]; then
  API_SERVICES+=(commercial-api)
  MIGRATE_TARGETS+=(commercial-api)
fi
ALL_IMAGES=("${API_SERVICES[@]}" "${WEB_APPS[@]}")

echo "== 0. unpark PostgreSQL (idempotent) =="
az postgres flexible-server start -g "$RG" -n "psql-dijione-${ENV}" -o none 2>/dev/null || true

echo "== 1. FOUNDATION =="
az deployment group create -g "$RG" -n "dijione-foundation-${GITSHA}" \
  -f "$BICEP_DIR/foundation.bicep" -p "$BICEP_DIR/foundation.${ENV}.bicepparam" \
  -o none

echo "== 2. BUILD ONCE into $ACR + record digests =="
DIGESTS="{"
sep=""
build_one() {  # $1 = service, $2 = dockerfile, $3 = build-arg name
  az acr build -r "$ACR" -f "deploy/$2" --build-arg "$3=$1" \
    -t "dijione/$1:$GITSHA" "$REPO_ROOT" -o none
  local d
  d="$(az acr repository show -n "$ACR" --image "dijione/$1:$GITSHA" --query digest -o tsv)"
  [ -n "$d" ] || { echo "!! no digest for dijione/$1:$GITSHA" >&2; exit 1; }
  DIGESTS="${DIGESTS}${sep}\"$1\":\"$d\""
  sep=","
  echo "   dijione/$1  $d"
}
for svc in "${API_SERVICES[@]}"; do build_one "$svc" Dockerfile.api SERVICE; done
for app in "${WEB_APPS[@]}"; do build_one "$app" Dockerfile.web APP; done
DIGESTS="${DIGESTS}}"

echo "== 3. assert Key Vault secrets are set (init-secrets.sh writes them) =="
mapfile -t EXPECTED < <(az deployment group show -g "$RG" -n "dijione-foundation-${GITSHA}" \
  --query 'properties.outputs.expectedSecretNames.value' -o tsv | tr '\t' '\n')
for name in "${EXPECTED[@]}"; do
  [ -n "$name" ] || continue
  v="$(az keyvault secret show --vault-name "kv-dijione-${ENV}" -n "$name" --query value -o tsv 2>/dev/null || echo "")"
  if [ -z "$v" ] || [ "$v" = "set-me-via-deploy.sh" ]; then
    echo "!! Key Vault secret '$name' is unset. Run: deploy/init-secrets.sh ${ENV}" >&2
    exit 1
  fi
done

echo "== 4. WORKLOADS (deploy by immutable digest) =="
az deployment group create -g "$RG" -n "dijione-workloads-${GITSHA}" \
  -f "$BICEP_DIR/main.bicep" -p "$BICEP_DIR/main.${ENV}.bicepparam" \
  -p imageDigests="$DIGESTS" \
  -o none

echo "== 5. per-service env (internal URLs, modes) =="
az containerapp update -g "$RG" -n shell-web --set-env-vars \
  ADMIN_WEB_URL=http://admin-web TALENT_WEB_URL=http://talent-web BIRTHDAY_WEB_URL=http://birthday-web \
  PLATFORM_API_URL=http://platform-api ADMIN_API_URL=http://admin-api TALENT_API_URL=http://talent-api \
  BIRTHDAY_API_URL=http://birthday-api SPARK_API_URL=http://spark-api -o none
az containerapp update -g "$RG" -n admin-api --set-env-vars \
  PLATFORM_API_URL=http://platform-api TALENT_API_URL=http://talent-api -o none
az containerapp update -g "$RG" -n platform-api --set-env-vars \
  AUTH_MODE=dev DEV_IDENTITY_MODE=true TALENT_API_URL=http://talent-api -o none
az containerapp update -g "$RG" -n talent-api --set-env-vars \
  PLATFORM_API_URL=http://platform-api RECRUITMENT_API_URL=http://recruitment-api -o none
az containerapp update -g "$RG" -n recruitment-api --set-env-vars \
  PLATFORM_API_URL=http://platform-api OPPORTUNITY_SYNC_LIMIT=200 -o none
if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  az containerapp update -g "$RG" -n people-api --set-env-vars PLATFORM_API_URL=http://platform-api -o none
  az containerapp update -g "$RG" -n birthday-api --set-env-vars \
    PLATFORM_API_URL=http://platform-api PEOPLE_API_URL=http://people-api -o none
  az containerapp update -g "$RG" -n birthday-web --set-env-vars \
    PLATFORM_API_URL=http://platform-api BIRTHDAY_API_URL=http://birthday-api -o none
fi
az containerapp update -g "$RG" -n admin-web --set-env-vars \
  PLATFORM_API_URL=http://platform-api ADMIN_API_URL=http://admin-api -o none
az containerapp update -g "$RG" -n talent-web --set-env-vars \
  PLATFORM_API_URL=http://platform-api TALENT_API_URL=http://talent-api -o none
az containerapp update -g "$RG" -n talentflow-portal-web --set-env-vars \
  TALENT_API_URL=http://talent-api -o none

echo "== 6. run the per-service migrate jobs (schema owner runs its own) =="
for t in "${MIGRATE_TARGETS[@]}"; do
  echo "  -> migrate-$t"
  az containerapp job start -g "$RG" -n "migrate-$t" -o none
done
echo "  (poll: az containerapp job execution list -g $RG -n migrate-<svc>)"

echo "== 7. smoke: /health/deep on each backend =="
for svc in "${API_SERVICES[@]}"; do
  echo "--- $svc ---"
  az containerapp exec -g "$RG" -n "$svc" --command "curl -s localhost:8000/health/deep" || true
done

echo
echo "shell-web:      $(az containerapp show -g "$RG" -n shell-web --query properties.configuration.ingress.fqdn -o tsv)"
echo "client portal:  $(az containerapp show -g "$RG" -n talentflow-portal-web --query properties.configuration.ingress.fqdn -o tsv)"
[ "$DEPLOY_BIRTHDAY" = "true" ] && \
echo "supplier portal:$(az containerapp show -g "$RG" -n birthday-supplier-web --query properties.configuration.ingress.fqdn -o tsv)"
echo
echo "recorded digests (promote these exactly, never rebuild):"
echo "$DIGESTS"
