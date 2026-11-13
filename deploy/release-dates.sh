#!/usr/bin/env bash
# Build main.bicep's `releaseDates` parameter WITHOUT erasing anything.
#
#   deploy/release-dates.sh <resource-group>
#   RELEASE_APPS=birthday-api,birthday-web deploy/release-dates.sh rg-dijione-uat
#
# Container Apps `env` is desired-state, so a main.bicep run erases any
# RELEASE_DATE it is not told about (docs/platform/versioning.md). This script:
#   1. reads every Container App's live RELEASE_DATE in <resource-group>,
#   2. carries each one forward unchanged,
#   3. stamps now (UTC) ONLY for the apps named in RELEASE_APPS — the explicit
#      release targets of this run, never inferred from a diff,
# and prints the JSON object on stdout. Read-only against Azure.
set -euo pipefail
RG="${1:?usage: release-dates.sh <resource-group>}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

LIVE_TSV="$(az containerapp list -g "$RG" \
  --query "[].{n:name, d:properties.template.containers[0].env[?name=='RELEASE_DATE'].value | [0]}" \
  -o tsv)"

python3 - "$NOW" "${RELEASE_APPS:-}" <<PY
import json, sys
now, release_apps = sys.argv[1], [a for a in sys.argv[2].split(",") if a.strip()]
dates = {}
for line in """$LIVE_TSV""".splitlines():
    parts = line.split("\t")
    if len(parts) == 2 and parts[1] and parts[1] != "None":
        dates[parts[0]] = parts[1]
for app in release_apps:
    dates[app.strip()] = now
print(json.dumps(dates, sort_keys=True))
PY
