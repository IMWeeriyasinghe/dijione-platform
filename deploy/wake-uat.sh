#!/usr/bin/env bash
# UAT wrapper — see wake-dev.sh. Set WARM=1 to pre-warm. Unparks psql-dijione-uat.
exec "$(dirname "$0")/wake-dev.sh" uat
