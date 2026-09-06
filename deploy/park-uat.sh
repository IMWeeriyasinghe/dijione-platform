#!/usr/bin/env bash
# UAT wrapper — see park-dev.sh. Parks psql-dijione-uat outside test windows.
exec "$(dirname "$0")/park-dev.sh" uat
