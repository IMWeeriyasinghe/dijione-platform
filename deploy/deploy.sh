#!/usr/bin/env bash
# DijiOne deploy — operator-run, one environment at a time. No CI/CD yet.
#
#   ./deploy/deploy.sh <env> <gitsha>
#
# Requires: az login on a subscription with spend approved; the RG
# rg-dijione-<env> already created; the Key Vault secret VALUES already set
# (this script does NOT create secret values — see step 2).
#
# Immutable-artifact model: builds each image once as :<gitsha>, and the
# SAME <gitsha> is promoted DEV -> UAT -> PROD by re-running this with a
# different <env>. Never rebuild from source per environment.
#
# NOTHING here is run during planning. This is the Phase 1+ runbook.

set -euo pipefail

ENV="${1:?usage: deploy.sh <env> <gitsha>}"
GITSHA="${2:?usage: deploy.sh <env> <gitsha>}"
RG="rg-dijione-${ENV}"
ACR="crdijione${ENV}"
BICEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/bicep" && pwd)"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

echo "== 0. start PostgreSQL (in case it was stopped for cost) =="
az postgres flexible-server start -g "$RG" -n "psql-dijione-${ENV}" -o none 2>/dev/null || true

echo "== 1. build + push images :$GITSHA (server-side, no local Docker) =="
for svc in "${API_SERVICES[@]}"; do
  az acr build -r "$ACR" -f deploy/Dockerfile.api --build-arg SERVICE="$svc" \
    -t "dijione/$svc:$GITSHA" -t "dijione/$svc:$ENV" "$REPO_ROOT"
done
for app in "${WEB_APPS[@]}"; do
  az acr build -r "$ACR" -f deploy/Dockerfile.web --build-arg APP="$app" \
    -t "dijione/$app:$GITSHA" -t "dijione/$app:$ENV" "$REPO_ROOT"
done

echo "== 2. secret VALUES must already be set (fail loudly if not) =="
for name in jwt-dev-secret internal-service-secret external-session-jwt-secret; do
  v=$(az keyvault secret show --vault-name "kv-dijione-${ENV}" -n "$name" --query value -o tsv 2>/dev/null || echo "")
  if [ -z "$v" ] || [ "$v" = "set-me-via-deploy.sh" ]; then
    echo "!! Key Vault secret '$name' is unset. Set it first, e.g.:"
    echo "   az keyvault secret set --vault-name kv-dijione-${ENV} -n $name --value <high-entropy>"
    exit 1
  fi
done

echo "== 3. deploy infra + apps (Bicep) =="
az deployment group create -g "$RG" \
  -f "$BICEP_DIR/main.bicep" -p "$BICEP_DIR/main.${ENV}.bicepparam" \
  -p imageTag="$GITSHA" \
  -o none

echo "== 4. per-service env (internal URLs, modes) =="
# The internal *_API_URL / *_WEB_URL values (http://<name>) and per-service
# extras from each .env.example. Kept out of Bicep so a URL change is one
# `az containerapp update`, not a full redeploy.
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

echo "== 5. run the per-service migrate jobs (schema owner runs its own) =="
for t in "${MIGRATE_TARGETS[@]}"; do
  echo "  -> migrate-$t"
  az containerapp job start -g "$RG" -n "migrate-$t" -o none
done
echo "  (poll: az containerapp job execution list -g $RG -n migrate-<svc>)"

echo "== 6. smoke: /health/deep on each backend =="
for svc in "${API_SERVICES[@]}"; do
  echo "--- $svc ---"
  az containerapp exec -g "$RG" -n "$svc" --command "curl -s localhost:8000/health/deep" || true
done

echo
echo "shell-web:      $(az containerapp show -g "$RG" -n shell-web --query properties.configuration.ingress.fqdn -o tsv)"
echo "client portal:  $(az containerapp show -g "$RG" -n talentflow-portal-web --query properties.configuration.ingress.fqdn -o tsv)"
[ "$DEPLOY_BIRTHDAY" = "true" ] && \
echo "supplier portal:$(az containerapp show -g "$RG" -n birthday-supplier-web --query properties.configuration.ingress.fqdn -o tsv)"
