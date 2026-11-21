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

fail_closed() {  # any az error other than "not found" stops the deploy: never compare against nothing
  echo "!! mail-config-guard: cannot read $1 from Azure (${2:-az error}); refusing to continue" >&2
  echo "   fix the az login/subscription, or set ALLOW_MAIL_CONFIG_CHANGE=1 to override deliberately" >&2
  [ "${ALLOW_MAIL_CONFIG_CHANGE:-0}" = "1" ] || exit 1
}

first_error() {  # first meaningful stderr line: Azure CLI WARNING lines are not the error
  grep -v -E '^[[:space:]]*(WARNING:|$)' "$1" | head -1 || true
}

live_env() {  # value of env var $2 on container app $1 ('' when unset); fails closed on az error
  # stdout carries the value; stderr (az extension/preview WARNING lines, errors) goes to a
  # separate file and is NEVER compared — mixing the two once reported a false drift.
  local out errf
  errf="$(mktemp)"
  if ! out="$(az containerapp show -g "$RG" -n "$1" \
      --query "properties.template.containers[0].env[?name=='$2'].value | [0]" -o tsv 2>"$errf")"; then
    fail_closed "$1 $2" "$(first_error "$errf")"; out=""
  fi
  rm -f "$errf"
  out="${out%$'\r'}"
  case "$out" in  # a single env value is one line; anything else is not a result we understand
    *$'\n'*|*$'\r'*) fail_closed "$1 $2" "malformed az result"; out="" ;;
  esac
  printf '%s' "$out"
}

drift=0
for row in "${SERVICES[@]}"; do
  IFS='|' read -r svc p_transport p_policy p_mailbox <<<"$row"
  if ! err="$(az containerapp show -g "$RG" -n "$svc" --query name -o tsv 2>&1 >/dev/null)"; then
    if printf '%s' "$err" | grep -qiE 'ResourceNotFound|was not found|could not be found'; then
      echo "   $svc: not deployed yet — nothing to compare"
      continue
    fi
    fail_closed "$svc" "$(printf '%s\n' "$err" | grep -v -E '^[[:space:]]*(WARNING:|$)' | head -1 || true)"
    continue
  fi
  svc_drift=0
  want_transport="$(param_value "$p_transport")"
  # main.bicep emits no MAIL_* at all when the transport parameter is empty.
  if [ -z "$want_transport" ]; then want_policy=""; want_mailbox=""; else
    want_policy="$(param_value "$p_policy")"; want_mailbox="$(param_value "$p_mailbox")"; fi
  for pair in "MAIL_TRANSPORT|$want_transport" "MAIL_POLICY|$want_policy" "MAIL_SHARED_MAILBOX|$want_mailbox"; do
    var="${pair%%|*}"; want="${pair#*|}"
    have="$(live_env "$svc" "$var")" || exit 1
    if [ "$have" != "$want" ]; then
      echo "!! $svc $var: live='${have:-<unset>}' would become '${want:-<unset>}'" >&2
      drift=1; svc_drift=1
    fi
  done
  [ "$svc_drift" -eq 0 ] && echo "   $svc: mail configuration unchanged (transport='${want_transport:-<unset>}')"
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
