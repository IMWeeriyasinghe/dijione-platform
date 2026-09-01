#!/usr/bin/env bash
# Provision the DijiOne DEV on Azure Container Apps + PostgreSQL Flexible.
# Idempotent-ish: re-running `create` on an existing resource is a no-op or a
# harmless error. Edit the variables below, then: ./deploy/provision.sh
#
# Nothing here is destructive except an explicit `az group delete` (not run).
# See deploy/README.md for the full runbook (secrets, env, Entra, smoke).

set -euo pipefail

# ---- edit these ----------------------------------------------------------
RG="rg-dijione-dev"
LOCATION="australiaeast"
ENVIRONMENT="cae-dijione-dev"
LAW="law-dijione-dev"
PG="psql-dijione-dev"
PG_ADMIN="dijione"
PG_PASSWORD="${PG_PASSWORD:?set PG_PASSWORD in the environment, do not commit it}"
REGISTRY="${REGISTRY:?set REGISTRY, e.g. ghcr.io/<you> or <acr>.azurecr.io}"
DEPLOY_BIRTHDAY="${DEPLOY_BIRTHDAY:-false}"   # people-api + birthday-api + birthday-web
DEPLOY_COMMERCIAL="${DEPLOY_COMMERCIAL:-false}"  # commercial-api skeleton
# -----------------------------------------------------------------------

# Core platform + the two source domains DijiTalentFlow depends on.
API_SERVICES=(platform-api admin-api talent-api recruitment-api)
WEB_SERVICES=(admin-web talent-web)
PG_DATABASES=(platform_dev talent_dev recruitment_dev)

if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  API_SERVICES+=(people-api birthday-api)
  WEB_SERVICES+=(birthday-web)
  PG_DATABASES+=(people_dev birthday_dev)
fi
if [ "$DEPLOY_COMMERCIAL" = "true" ]; then
  API_SERVICES+=(commercial-api)
  PG_DATABASES+=(commercial_dev)
fi

echo "==> resource group"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> log analytics"
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOCATION" -o none
LAW_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query customerId -o tsv)
LAW_KEY=$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LAW" --query primarySharedKey -o tsv)

echo "==> container apps environment"
az containerapp env create -g "$RG" -n "$ENVIRONMENT" -l "$LOCATION" \
  --logs-workspace-id "$LAW_ID" --logs-workspace-key "$LAW_KEY" -o none

echo "==> postgres flexible server (Burstable B1ms) + one database per domain"
az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOCATION" \
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 \
  --admin-user "$PG_ADMIN" --admin-password "$PG_PASSWORD" \
  --public-access 0.0.0.0 --yes -o none
for db in "${PG_DATABASES[@]}"; do
  az postgres flexible-server db create -g "$RG" -s "$PG" -d "$db" -o none
done
az postgres flexible-server firewall-rule create -g "$RG" -n "$PG" \
  --rule-name allow-azure --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none

echo "==> container apps (internal-ingress APIs)"
for svc in "${API_SERVICES[@]}"; do
  az containerapp create -g "$RG" -n "$svc" --environment "$ENVIRONMENT" \
    --image "$REGISTRY/dijione/$svc:latest" \
    --ingress internal --target-port 8000 \
    --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 2 -o none
done

echo "==> container apps (internal-ingress web zones)"
for app in "${WEB_SERVICES[@]}"; do
  az containerapp create -g "$RG" -n "$app" --environment "$ENVIRONMENT" \
    --image "$REGISTRY/dijione/$app:latest" \
    --ingress internal --target-port 3000 \
    --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 2 -o none
done

echo "==> container app (external gateway: shell-web — the ONLY external ingress)"
az containerapp create -g "$RG" -n shell-web --environment "$ENVIRONMENT" \
  --image "$REGISTRY/dijione/shell-web:latest" \
  --ingress external --target-port 3000 \
  --cpu 0.25 --memory 0.5Gi --min-replicas 1 --max-replicas 3 -o none

echo "==> scheduled source-sync Jobs (replica-safe — NOT an in-process timer)"
# Recruitment Source: reconcile Lever every 6 hours.
az containerapp job create -g "$RG" -n recruitment-sync-job --environment "$ENVIRONMENT" \
  --image "$REGISTRY/dijione/recruitment-api:latest" \
  --trigger-type Schedule --cron-expression "0 */6 * * *" \
  --replica-timeout 1800 --replica-retry-limit 1 --parallelism 1 \
  --cpu 0.25 --memory 0.5Gi \
  --command "/bin/sh" --args "-c","curl -fsS -X POST -H \"X-Internal-Token: \$INTERNAL_SERVICE_SECRET\" -H \"X-Internal-Caller: recruitment-sync-job\" http://recruitment-api/api/recruitment/internal/scheduled-sync" -o none

# DijiTalentFlow: refresh its posting projection + DTC trust reconciliation,
# offset 15 min after the recruitment sync so it sees fresh data.
az containerapp job create -g "$RG" -n talent-reconcile-job --environment "$ENVIRONMENT" \
  --image "$REGISTRY/dijione/talent-api:latest" \
  --trigger-type Schedule --cron-expression "15 */6 * * *" \
  --replica-timeout 900 --replica-retry-limit 1 --parallelism 1 \
  --cpu 0.25 --memory 0.5Gi \
  --command "/bin/sh" --args "-c","curl -fsS -X POST -H \"X-Internal-Token: \$INTERNAL_SERVICE_SECRET\" -H \"X-Internal-Caller: talent-reconcile-job\" http://talent-api/api/talent/internal/recruitment/reconcile" -o none

if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  # People / Workforce: reconcile BambooHR once a day (its approved cadence,
  # not Lever's 6h — birthday detection is date-bound, not stream-like).
  az containerapp job create -g "$RG" -n people-sync-job --environment "$ENVIRONMENT" \
    --image "$REGISTRY/dijione/people-api:latest" \
    --trigger-type Schedule --cron-expression "0 5 * * *" \
    --replica-timeout 1800 --replica-retry-limit 1 --parallelism 1 \
    --cpu 0.25 --memory 0.5Gi \
    --command "/bin/sh" --args "-c","curl -fsS -X POST -H \"X-Internal-Token: \$INTERNAL_SERVICE_SECRET\" -H \"X-Internal-Caller: people-sync-job\" http://people-api/api/people/internal/sync" -o none

  # DijiBirthday daily detection scan (external trigger — no in-process scheduler).
  az containerapp job create -g "$RG" -n birthday-scan-job --environment "$ENVIRONMENT" \
    --image "$REGISTRY/dijione/birthday-api:latest" \
    --trigger-type Schedule --cron-expression "30 5 * * *" \
    --replica-timeout 900 --replica-retry-limit 1 --parallelism 1 \
    --cpu 0.25 --memory 0.5Gi \
    --command "/bin/sh" --args "-c","curl -fsS -X POST -H \"X-Internal-Token: \$INTERNAL_SERVICE_SECRET\" -H \"X-Internal-Caller: birthday-scan-job\" http://birthday-api/api/birthday/internal/run-daily-scan" -o none
fi

echo
echo "==> NEXT: set secrets + env (deploy/README.md step 4), run migrations +"
echo "    seed (step 5), Entra Easy Auth (step 6), smoke test (step 7)."
echo "    shell-web URL:"
az containerapp show -g "$RG" -n shell-web --query properties.configuration.ingress.fqdn -o tsv
