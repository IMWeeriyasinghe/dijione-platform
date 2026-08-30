#!/usr/bin/env bash
# Provision the DijiOne meeting-DEV on Azure Container Apps + PostgreSQL.
# Idempotent-ish: re-running `create` on an existing resource is a no-op or a
# harmless error. Edit the variables below, then: ./deploy/provision.sh
#
# Nothing here is destructive except an explicit `az group delete` (not run).

set -euo pipefail

# ---- edit these ------------------------------------------------------------
RG="rg-dijione-dev"
LOCATION="australiaeast"
ENVIRONMENT="cae-dijione-dev"
LAW="law-dijione-dev"
PG="psql-dijione-dev"
PG_ADMIN="dijione"
PG_PASSWORD="${PG_PASSWORD:?set PG_PASSWORD in the environment, do not commit it}"
REGISTRY="${REGISTRY:?set REGISTRY, e.g. ghcr.io/<you> or <acr>.azurecr.io}"
DEPLOY_BIRTHDAY="${DEPLOY_BIRTHDAY:-false}"
# -------------------------------------------------------------------------

API_SERVICES=(platform-api admin-api talent-api)
WEB_SERVICES=(admin-web talent-web)
if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  API_SERVICES+=(birthday-api)
  WEB_SERVICES+=(birthday-web)
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

echo "==> postgres flexible server (Burstable B1ms)"
az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOCATION" \
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 \
  --admin-user "$PG_ADMIN" --admin-password "$PG_PASSWORD" \
  --public-access 0.0.0.0 --yes -o none
az postgres flexible-server db create -g "$RG" -s "$PG" -d platform_dev -o none
az postgres flexible-server db create -g "$RG" -s "$PG" -d talent_dev -o none
if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  az postgres flexible-server db create -g "$RG" -s "$PG" -d birthday_dev -o none
fi
az postgres flexible-server firewall-rule create -g "$RG" -n "$PG" \
  --rule-name allow-azure --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none

echo "==> container apps (internal APIs)"
for svc in "${API_SERVICES[@]}"; do
  az containerapp create -g "$RG" -n "$svc" --environment "$ENVIRONMENT" \
    --image "$REGISTRY/dijione/$svc:latest" \
    --ingress internal --target-port 8000 \
    --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 2 -o none
done

echo "==> container apps (internal zones)"
for app in "${WEB_SERVICES[@]}"; do
  az containerapp create -g "$RG" -n "$app" --environment "$ENVIRONMENT" \
    --image "$REGISTRY/dijione/$app:latest" \
    --ingress internal --target-port 3000 \
    --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 2 -o none
done

echo "==> container app (external gateway: shell-web)"
az containerapp create -g "$RG" -n shell-web --environment "$ENVIRONMENT" \
  --image "$REGISTRY/dijione/shell-web:latest" \
  --ingress external --target-port 3000 \
  --cpu 0.25 --memory 0.5Gi --min-replicas 1 --max-replicas 3 -o none

echo
echo "==> NEXT: set secrets + env (deploy/README.md step 4), bootstrap (step 5),"
echo "    Entra Easy Auth (step 6). shell-web URL:"
az containerapp show -g "$RG" -n shell-web --query properties.configuration.ingress.fqdn -o tsv
