#!/usr/bin/env bash
# DijiOne DEV unpark (Amendment 8). Starts the PostgreSQL Flexible Server that
# park-dev.sh stopped, then optionally pre-warms platform-api so the first
# real request does not eat the chained cold start (shell-web -> platform-api
# -> Postgres). Container Apps wake themselves on first request.
#
#   ./deploy/wake-dev.sh          # ENV defaults to dev; set WARM=1 to pre-warm
set -euo pipefail
ENV="${1:-dev}"
RG="rg-dijione-${ENV}"

echo "starting psql-dijione-${ENV} (1-3 min)..."
az postgres flexible-server start -g "$RG" -n "psql-dijione-${ENV}" -o none

if [ "${WARM:-0}" = "1" ]; then
  echo "pre-warming platform-api + shell-web..."
  for app in platform-api shell-web; do
    fqdn="$(az containerapp show -g "$RG" -n "$app" --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null || true)"
    [ -n "$fqdn" ] && curl -fsS "https://${fqdn}/health" -o /dev/null || true
  done
fi
echo "psql-dijione-${ENV} running. DEV is live."
