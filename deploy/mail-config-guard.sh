#!/usr/bin/env bash
# Mail configuration drift guard — run BEFORE a full main.bicep deployment.
#
# Container App env is desired-state: a full deployment replaces each app's env array. If the
# live MAIL_* settings of an email-sending service differ from what the .bicepparam declares,
# the deployment would silently switch that service's email on or off (this happened once to
# birthday-api in PROD). This guard compares, read-only, the live values with the values the
# param file will produce, and stops the deployment on any difference.
#
#   deploy/mail-config-guard.sh <resource-group> <path/to/main.<env>.bicepparam>
#
# Exit 0: no difference (or a service not deployed yet). Exit 1: difference — update the
# .bicepparam deliberately (that is a reviewed change), or, only when the change of state is
# itself the intent of this deployment, re-run with ALLOW_MAIL_CONFIG_CHANGE=1.
#
# Reads only: `az containerapp show`. Never changes anything.
set -euo pipefail

RG="${1:?usage: mail-config-guard.sh <resource-group> <bicepparam>}"
PARAMS="${2:?usage: mail-config-guard.sh <resource-group> <bicepparam>}"

# service | MAIL_TRANSPORT param | MAIL_POLICY param | MAIL_SHARED_MAILBOX param
SERVICES=(
  "birthday-api|birthdayMailTransport|birthdayMailPolicy|birthdayMailSharedMailbox"
  "platform-api|platformMailTransport|platformMailPolicy|platformMailSharedMailbox"
)

param_value() {  # value of `param <name> = '<value>'` in the .bicepparam ('' when absent)
  sed -nE "s/^[[:space:]]*param[[:space:]]+$1[[:space:]]*=[[:space:]]*'([^']*)'.*/\1/p" "$PARAMS" | tail -1
}

live_env() {  # value of env var $2 on container app $1 ('' when unset)
  az containerapp show -g "$RG" -n "$1" \
    --query "properties.template.containers[0].env[?name=='$2'].value | [0]" -o tsv 2>/dev/null || true
}

drift=0
for row in "${SERVICES[@]}"; do
  IFS='|' read -r svc p_transport p_policy p_mailbox <<<"$row"
  if ! az containerapp show -g "$RG" -n "$svc" --query name -o tsv >/dev/null 2>&1; then
    echo "   $svc: not deployed yet — nothing to compare"
    continue
  fi
  want_transport="$(param_value "$p_transport")"
  # main.bicep emits no MAIL_* at all when the transport parameter is empty.
  if [ -z "$want_transport" ]; then want_policy=""; want_mailbox=""; else
    want_policy="$(param_value "$p_policy")"; want_mailbox="$(param_value "$p_mailbox")"; fi
  for pair in "MAIL_TRANSPORT|$want_transport" "MAIL_POLICY|$want_policy" "MAIL_SHARED_MAILBOX|$want_mailbox"; do
    var="${pair%%|*}"; want="${pair#*|}"
    have="$(live_env "$svc" "$var")"
    if [ "$have" != "$want" ]; then
      echo "!! $svc $var: live='${have:-<unset>}' would become '${want:-<unset>}'" >&2
      drift=1
    fi
  done
  [ "$drift" -eq 0 ] && echo "   $svc: mail configuration unchanged (transport='${want_transport:-<unset>}')"
done

if [ "$drift" -ne 0 ]; then
  if [ "${ALLOW_MAIL_CONFIG_CHANGE:-0}" = "1" ]; then
    echo "   ALLOW_MAIL_CONFIG_CHANGE=1: proceeding with the mail configuration change above"
    exit 0
  fi
  echo "!! Stopping: this deployment would change live email sending. Update $PARAMS to match," >&2
  echo "   or set ALLOW_MAIL_CONFIG_CHANGE=1 if changing it is the approved intent." >&2
  exit 1
fi
