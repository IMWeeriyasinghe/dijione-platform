#!/usr/bin/env bash
# Build the DijiOne application images ONCE into a registry and record their
# immutable sha256 digests. Does NOT deploy, does NOT touch Key Vault, does NOT
# create Container Apps / Jobs. This is deploy.sh's build stage, extracted so it
# can be run in isolation (Phase 2A).
#
#   ./deploy/build-images.sh <acr-name> <gitsha> [digests-out-file]
#
#   DEPLOY_BIRTHDAY   default true  -> also builds people/birthday images
#   DEPLOY_COMMERCIAL default false -> commercial-api is NEVER built here
#
# Idempotent: an image whose <gitsha> tag already resolves to a digest is not
# rebuilt. The out-file gets one  "<service>\t<gitsha>\t<sha256:digest>"  line
# per image (defaults to stdout).

set -euo pipefail

ACR="${1:?usage: build-images.sh <acr-name> <gitsha> [out]}"
GITSHA="${2:?usage: build-images.sh <acr-name> <gitsha> [out]}"
OUT="${3:-/dev/stdout}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DEPLOY_BIRTHDAY="${DEPLOY_BIRTHDAY:-true}"
DEPLOY_COMMERCIAL="${DEPLOY_COMMERCIAL:-false}"

API_SERVICES=(platform-api admin-api talent-api recruitment-api)
WEB_APPS=(shell-web admin-web talent-web talentflow-portal-web)
if [ "$DEPLOY_BIRTHDAY" = "true" ]; then
  API_SERVICES+=(people-api birthday-api)
  WEB_APPS+=(birthday-web birthday-supplier-web)
fi
if [ "$DEPLOY_COMMERCIAL" = "true" ]; then
  API_SERVICES+=(commercial-api)   # spark-api is never deployed and never built
fi

: > "$OUT"

# Resolve the immutable digest of dijione/<svc>:<GITSHA>, or empty if the tag
# is absent. `az acr repository show --image` is intermittently flaky under
# rapid calls, so confirm the tag via show-tags first and retry the digest.
digest_of() {
  local svc="$1" i d
  az acr repository show-tags -n "$ACR" --repository "dijione/$svc" -o tsv 2>/dev/null \
    | grep -qx "$GITSHA" || return 0
  for i in 1 2 3; do
    d="$(az acr repository show -n "$ACR" --image "dijione/$svc:$GITSHA" --query digest -o tsv 2>/dev/null || true)"
    [ -n "$d" ] && { printf '%s' "$d"; return 0; }
    sleep 2
  done
  return 0
}

build_one() {  # $1 service  $2 dockerfile  $3 build-arg name
  local svc="$1" dockerfile="$2" arg="$3" d
  d="$(digest_of "$svc")"
  if [ -z "$d" ]; then
    echo ">> building dijione/$svc:$GITSHA"
    az acr build -r "$ACR" -f "deploy/$dockerfile" --build-arg "$arg=$svc" \
      -t "dijione/$svc:$GITSHA" "$REPO_ROOT" -o none
    d="$(digest_of "$svc")"
  else
    echo ">> dijione/$svc:$GITSHA already present, skipping"
  fi
  [ -n "$d" ] || { echo "!! no digest for dijione/$svc:$GITSHA" >&2; exit 1; }
  printf '%s\t%s\t%s\n' "$svc" "$GITSHA" "$d" >> "$OUT"
  echo "   $svc  $d"
}

for s in "${API_SERVICES[@]}"; do build_one "$s" Dockerfile.api SERVICE; done
for a in "${WEB_APPS[@]}"; do build_one "$a" Dockerfile.web APP; done

echo "== built/verified $(grep -c . "$OUT" 2>/dev/null || wc -l < "$OUT") images into $ACR =="
