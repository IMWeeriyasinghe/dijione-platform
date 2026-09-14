#!/usr/bin/env bash
# Build and push every DijiOne image. Run from the repo root.
#   REGISTRY=ghcr.io/<you> ./deploy/build-push.sh
#   REGISTRY=<acr>.azurecr.io DEPLOY_BIRTHDAY=true ./deploy/build-push.sh
#
# Auth to the registry first (docker login ghcr.io  |  az acr login -n <acr>).

set -euo pipefail

REGISTRY="${REGISTRY:?set REGISTRY, e.g. ghcr.io/<you> or <acr>.azurecr.io}"
TAG="${TAG:-latest}"
DEPLOY_BIRTHDAY="${DEPLOY_BIRTHDAY:-false}"
DEPLOY_COMMERCIAL="${DEPLOY_COMMERCIAL:-false}"

# Per-app footer version/build metadata (docs/platform/versioning.md).
GIT_SHA="${GIT_SHA:-$(git rev-parse --short=12 HEAD)}"
BUILD_DATE="${BUILD_DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

# talentflow-portal-web is the external Client Talent Review Workspace —
# always part of DijiTalentFlow, its own hostname, not proxied through shell-web.
API_SERVICES=(platform-api admin-api talent-api recruitment-api)
WEB_APPS=(shell-web admin-web talent-web talentflow-portal-web)
if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  API_SERVICES+=(people-api birthday-api)
  WEB_APPS+=(birthday-web birthday-supplier-web)
fi
if [ "$DEPLOY_COMMERCIAL" = "true" ]; then
  API_SERVICES+=(commercial-api)
fi

for svc in "${API_SERVICES[@]}"; do
  echo "==> build $svc"
  docker build -f deploy/Dockerfile.api --build-arg SERVICE="$svc" \
    -t "$REGISTRY/dijione/$svc:$TAG" .
  docker push "$REGISTRY/dijione/$svc:$TAG"
done

for app in "${WEB_APPS[@]}"; do
  echo "==> build $app"
  docker build -f deploy/Dockerfile.web --build-arg APP="$app" \
    --build-arg GIT_SHA="$GIT_SHA" --build-arg BUILD_DATE="$BUILD_DATE" \
    -t "$REGISTRY/dijione/$app:$TAG" .
  docker push "$REGISTRY/dijione/$app:$TAG"
done

echo "==> done"
