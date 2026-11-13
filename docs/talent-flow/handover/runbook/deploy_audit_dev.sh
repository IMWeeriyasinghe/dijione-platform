#!/bin/bash
# DEV audit infrastructure runbook (hardened). Only `preflight` is read-only.
# Every other phase mutates DEV and needs explicit approval.
# Usage: deploy_audit_dev.sh <phase>. Each phase checks its prerequisites, and
# its safety gates are enforced in code: any failure exits non-zero and stops.
# Scope: rg-dijione-dev. Mutated: platform-api, migrate-platform-api, talent-api,
# migrate-talent-api, new talent-audit-outbox-job, ACR delete-locks, one DB backup.
set -euo pipefail
export MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8
G=rg-dijione-dev; R=crdijionenonprod; A=$R.azurecr.io/dijione; PG=psql-dijione-dev; JOB=talent-audit-outbox-job
ROOT="C:/Projects/Diji Projects/DijiOne/dijione-platform"
H="$(cygpath -m "$(cd "$(dirname "$0")" && pwd)")/audit-runbook"; ST="$H/state"; mkdir -p "$ST"
P_SHA=6f2d6be81eff6ed6724bc5d798e400d4923ea86a   # PR #91 (isolated Platform)
T_SHA=9b35f43f185aaeda53677d229aa1d7cfb331ae30   # PR #90 (Talent outbox)
P_OLD=sha256:a58d2cb14d425a62e9e9896a86fa0ab01ca59efda640f269237db238a0d049c7    # platform-api--0000023 + migrate-platform-api
T_OLD=sha256:c146a57ed6a0b77ef67340b972e3d3dd999dd9a8905ec8491d44a72f04ee810d    # talent-api--0000015
TM_OLD=sha256:ad5776134a1af26c05bdfc65240a5de6839dc12be10ffc9e80ee94fc46e2919b   # migrate-talent-api
P_HEAD_OLD=o5p6q7r8s9t0; P_HEAD_NEW=a7e1d0c4b9f2; T_HEAD_OLD=b3c5d7e9f1a2; T_HEAD_NEW=c4d6e8f0a2b3
UNTOUCHED_APPS="recruitment-api shell-web talent-web talentflow-portal-web"
UNTOUCHED_JOBS="talent-reconcile-job recruitment-sync-job bootstrap-talent-clients migrate-recruitment-api"

API=2026-07-01
job_url(){ echo "https://management.azure.com/subscriptions/$(az account show --query id -o tsv | tr -d '\r')/resourceGroups/$G/providers/Microsoft.App/jobs/$JOB"; }
log(){ echo "[$(date -u +%TZ)] $*" | tee -a "$ST/runbook.log"; }
stop(){ log "STOP: $*"; exit 1; }
need(){ for p; do [ -f "$ST/$p.ok" ] || stop "prerequisite '$p' has not completed"; done; }
ok(){ touch "$ST/$1.ok"; log "PHASE $1 COMPLETE"; }
py(){ python "$@"; }
app_json(){ az containerapp show -g $G -n "$1" -o json; }
job_json(){ az containerapp job show -g $G -n "$1" -o json; }
image_of(){ az containerapp ${2:-} show -g $G -n "$1" --query "properties.template.containers[0].image" -o tsv | tr -d '\r'; }

# Run a helper inside a container app; extract the TAG-prefixed JSON line to OUT.
inapp(){ local app=$1 script=$2 tag=$3 out=$4 src b
  src=$(sed -e "s/__RUN__/$(cat "$ST/run.id" 2>/dev/null || echo none)/g" -e "s/__MAXID__/$(cat "$ST/platform.maxid" 2>/dev/null || echo x)/g" -e "s/__MODE__/${MODE:-none}/g" -e "s/__SHA__/${SHA:-none}/g" -e "s|__CHUNK__|${CHUNK:-}|g" -e "s/__IDX__/${IDX:-0}/g" -e "s/__NCHUNK__/${NCHUNK:-0}/g" "$H/$script")
  b=$(printf '%s' "$src" | py -c "import base64,zlib,sys;print(base64.b64encode(zlib.compress(sys.stdin.buffer.read(),9)).decode())")
  local raw="$ST/exec.raw" try
  for try in 1 2 3 4 5 6; do
    local last; last=$(cat "$ST/exec.last" 2>/dev/null || echo 0); while [ $(( $(date -u +%s) - last )) -lt 90 ]; do sleep 5; done; date -u +%s > "$ST/exec.last"
    wake "$app"
    az containerapp exec -g $G -n "$app" --command "python -c \"import base64 as b,zlib as z;exec(z.decompress(b.b64decode('$b')))\"" > "$raw" 2>&1 || true
    tr -d '\033\r' < "$raw" | grep -a "^$tag " | head -1 | cut -d' ' -f2- > "$out" || true
    [ -s "$out" ] && return 0
    if grep -q "429 Too Many Requests" "$raw"; then log "exec throttled (429); waiting 610 s"; sleep 610; continue; fi
    grep -qE "Could not find a replica|Handshake status 404" "$raw" || break; sleep 30; done
  grep -aE "Error|Traceback|ERROR" "$raw" | tail -3 | cut -c1-200
  stop "$script in $app produced no $tag result"; }

# Start a detached C2 process in talent-api (rehearsal | run | run2) and poll it to a result.
c2_detached(){ local mode=$1 out=$2 E t=0 res=""
  # One-off execution of the existing audit job with a per-execution override (same image, identity, secrets);
  # the job definition and its schedule are not changed. The result line is read back from Log Analytics.
  local cpu=0.25 mem=0.5Gi
  local img; img=$(image_of $JOB job)
  if [ -s "$ST/c2.exec.$mode" ]; then E=$(cat "$ST/c2.exec.$mode"); log "C2 $mode resuming execution $E"
  else
    py - "$H/c2_body_$mode.py" "$img" "$cpu" "$mem" "$JOB" > "$ST/c2.start.$mode.yaml" <<'PYY'
import base64, json, sys, zlib
body, img, cpu, mem, job = sys.argv[1:6]
code = base64.b64encode(zlib.compress(open(body, "rb").read(), 9)).decode()
env = [{"name": "APP_ENV", "value": "development"}, {"name": "PLATFORM_API_URL", "value": "http://platform-api"},
       {"name": "RECRUITMENT_API_URL", "value": "http://recruitment-api"}, {"name": "INTEGRATIONS_MODE", "value": "mock"},
       {"name": "EMAIL_SENDING_MODE", "value": "mock"}, {"name": "DATABASE_URL", "secretRef": "database-url-talent"},
       {"name": "INTERNAL_SERVICE_SECRET", "secretRef": "internal-service-secret"}, {"name": "C2_CODE", "value": code}]
c = {"name": job, "image": img, "command": ["python"],
     "args": ["-c", "import base64,os,zlib;exec(zlib.decompress(base64.b64decode(os.environ['C2_CODE'])))"],
     "env": env, "resources": {"cpu": float(cpu), "memory": mem}}
print(json.dumps({"containers": [c]}))   # JSON is valid YAML
PYY
    E=$(az containerapp job start -g $G -n $JOB --yaml "$ST/c2.start.$mode.yaml" --query name -o tsv | tr -d '\r')
    [ -n "$E" ] || stop "C2 $mode execution did not start"; echo "$E" > "$ST/c2.exec.$mode"; log "C2 $mode execution $E"; fi
  wait_exec $JOB "$E" 400
  while :; do
    res=$(az monitor log-analytics query -w "$(cat "$ST/ws.id")" --analytics-query "ContainerAppConsoleLogs_CL | where ContainerJobName_s == '$JOB' and ContainerGroupName_s startswith '$E' and Log_s startswith 'C2R ' | top 1 by TimeGenerated | project Log_s" -o tsv 2>/dev/null | head -1 | cut -f1)
    [ -n "$res" ] && break
    [ $t -ge 600 ] && stop "C2 $mode result not found in logs after 600 s"; sleep 30; t=$((t+30)); done
  printf '%s' "${res#C2R }" | py -c "import json,sys;json.dump(json.loads(sys.stdin.read()),open(r'$out','w'))" || stop "C2 $mode result unreadable"
  log "C2 $mode finished: $(cut -c1-700 "$out")"; }

# Failed scheduled drains since activation. Scheduled executions have a numeric suffix;
# one-off override executions (C2 rehearsal/run, probe) are judged by their own gates.
sched_failed(){ az containerapp job execution list -g $G -n $JOB -o json | py -c "import json,sys,re;s=open(r'$ST/schedule.start').read().strip();print(sum(1 for e in json.load(sys.stdin) if re.search(r'-[0-9]+$',e['name']) and e['properties']['startTime']>=s and e['properties']['status'] not in ('Succeeded','Running','Processing')))"; }

# Scale-to-zero apps: one read-only GET through the DEV gateway starts a replica.
wake(){ local url; case "$1" in
    platform-api) url=https://dijione-dev.dijitalteam.com/api/auth/config ;;
    talent-api) url=https://dijione-dev.dijitalteam.com/api/talent/summary ;;
    *) return 0 ;; esac
  curl -s -o /dev/null --max-time 90 "$url" || true; }

# Reconcile must stay Suspended with nothing running, before and after every phase.
guard(){
  [ "$(az containerapp job show -g $G -n talent-reconcile-job --query properties.runningStatus -o tsv | tr -d '\r')" = Suspended ] || stop "talent-reconcile-job is not Suspended"
  local active; active=$(az containerapp job execution list -g $G -n talent-reconcile-job --query "length([?properties.status=='Running'||properties.status=='Processing'])" -o tsv | tr -d '\r')
  [ "$active" = 0 ] || stop "talent-reconcile-job has an active execution"; }

# Wait for a job execution to reach a terminal state; only Succeeded continues.
wait_exec(){ local job=$1 ex=$2 limit=${3:-1200} t=0 s
  while :; do
    s=$(az containerapp job execution show -g $G -n "$job" --job-execution-name "$ex" --query properties.status -o tsv | tr -d '\r')
    case "$s" in
      Succeeded) log "$job/$ex Succeeded"; return 0 ;;
      Failed|Stopped|Degraded|Cancelled|Canceled) stop "$job/$ex ended $s" ;;
    esac
    [ $t -ge $limit ] && stop "$job/$ex not terminal after ${limit}s (last: $s)"
    sleep 15; t=$((t+15)); done; }

# Wait for an app's newest revision to run the expected digest, be ready, Healthy and take all traffic.
wait_rev(){ local app=$1 digest=$2 t=0 v="" latest="" ready="" prov="" img="" health="" run="" traffic=""
  while :; do
    v=$(az containerapp show -g $G -n "$app" --query "[properties.latestRevisionName,properties.latestReadyRevisionName,properties.provisioningState,properties.template.containers[0].image]" -o tsv | tr -d '\r' | tr '\n' ' ')
    read -r latest ready prov img <<<"$v" || true
    if [ "$latest" = "$ready" ] && [ "$prov" = Succeeded ] && [ "$img" = "$A/$app@$digest" ]; then
      read -r health run traffic < <(az containerapp revision show -g $G -n "$app" --revision "$latest" --query "[properties.healthState,properties.runningState,properties.trafficWeight]" -o tsv | tr -d '\r' | tr '\n' ' ') || true
      if [ "$health" = Healthy ] && [ "$traffic" = 100 ] && [[ "$run" =~ ^(Running|RunningAtMaxScale)$ ]]; then log "$app $latest Healthy, ready, 100% traffic"; echo "$latest" > "$ST/$app.revision"; return 0; fi
      [ "$health" = Unhealthy ] && stop "$app $latest Unhealthy"
    fi
    [ $t -ge 600 ] && stop "$app not Healthy on $digest after 600s ($v $health $run $traffic)"
    sleep 15; t=$((t+15)); done; }

snap_platform(){ inapp platform-api in_platform_snapshot.py SNAP "$ST/platform.$1.json"; py "$H/gate.py" "platform-read-only-$1" "a['read_only']=='on'" "$ST/platform.$1.json"; }
snap_talent(){ inapp talent-api in_talent_snapshot.py SNAP "$ST/talent.$1.json"; py "$H/gate.py" "talent-read-only-$1" "a['read_only']=='on'" "$ST/talent.$1.json"; }
talent_unchanged(){ snap_talent "$1"; py "$H/gate.py" "talent-data-unchanged-$1" "strip(a)==strip(b)" "$ST/talent.baseline.json" "$ST/talent.$1.json"; }
platform_unchanged(){ py "$H/gate.py" "platform-data-preserved-$1" "a['baseline_rows_hash']==b['baseline_rows_hash'] and a['roles_hash']==b['roles_hash'] and a['clients_hash']==b['clients_hash'] and a['users']==b['users']" "$ST/platform.baseline.json" "$ST/platform.$1.json"; }
cfg_same(){ local kind=$1 name=$2 flag=${3:-}; [ "$kind" = app ] && app_json "$name" > "$ST/$name.after.json" || job_json "$name" > "$ST/$name.after.json"
  py "$H/cfgcmp.py" "$ST/$name.before.json" "$ST/$name.after.json" $flag || stop "$name configuration changed unexpectedly"; }
# Server Ready, PG16, Burstable B1ms, 7-day retention, an automatic backup completed in the last 24 h,
# and "now" inside the restore window. Records the recovery point as pitr.<tag>.json.
pitr_check(){ local tag=$1
  az postgres flexible-server show -g $G -n $PG -o json > "$ST/pg.server.json"
  az postgres flexible-server backup list -g $G -n $PG -o json > "$ST/pg.backups.json"
  py - "$ST" "$tag" <<'PY' || stop "PITR safeguard failed ($tag)"
import json, sys
from datetime import datetime, timedelta, timezone
st, tag = sys.argv[1:3]
s, b = json.load(open(f"{st}/pg.server.json")), json.load(open(f"{st}/pg.backups.json"))
now = datetime.now(timezone.utc)
ts = lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))
done = sorted(ts(x["completedTime"]) for x in b if x.get("completedTime"))
earliest = ts(s["backup"]["earliestRestoreDate"])
c = {"ready": s["state"] == "Ready", "pg16": str(s["version"]) == "16",
     "burstable_b1ms": s["sku"]["tier"] == "Burstable" and s["sku"]["name"] == "Standard_B1ms",
     "retention_7d": s["backup"]["backupRetentionDays"] == 7,
     "automatic_backup_24h": bool(done) and now - done[-1] < timedelta(hours=24),
     "recovery_point_in_window": earliest < now}
rec = {"ok": all(c.values()), **c, "earliest_restore": earliest.isoformat(), "latest_backup_completed": done[-1].isoformat() if done else None,
       "recovery_point": now.isoformat(timespec="seconds"), "note": "restore target, not a new backup"}
json.dump(rec, open(f"{st}/pitr.{tag}.json", "w"))
print("PITR " + json.dumps(rec)); sys.exit(0 if rec["ok"] else 1)
PY
  for d in "platform-api $P_OLD" "talent-api $T_OLD" "talent-api $TM_OLD"; do set -- $d
    [ "$(az acr manifest show-metadata -r $R -n dijione/$1@$2 --query changeableAttributes.deleteEnabled -o tsv | tr -d '\r')" = false ] || stop "rollback image $1@$2 lost its deletion protection"; done; }

manifest_ok(){ az acr manifest show-metadata -r $R -n "dijione/$1@$2" --query digest -o tsv 2>/dev/null | tr -d '\r' | grep -qx "$2"; }

case "${1:-}" in
preflight)   # READ-ONLY. Re-run immediately before any mutation; later phases require it to be < 2 h old.
  rm -f "$ST"/*.ok; guard
  [ "$(image_of platform-api)" = "$A/platform-api@$P_OLD" ] || stop "platform-api is not the verified baseline"
  [ "$(image_of migrate-platform-api job)" = "$A/platform-api@$P_OLD" ] || stop "migrate-platform-api is not the baseline"
  [ "$(image_of talent-api)" = "$A/talent-api@$T_OLD" ] || stop "talent-api is not the fail-closed baseline"
  [ "$(image_of migrate-talent-api job)" = "$A/talent-api@$TM_OLD" ] || stop "migrate-talent-api is not the recorded image"
  [ -z "$(az containerapp job list -g $G --query "[?name=='$JOB'].name" -o tsv)" ] || stop "$JOB already exists"
  [ "$(az containerapp show -g $G -n recruitment-api --query properties.template.scale.minReplicas -o tsv | tr -d '\r')" = 1 ] || stop "recruitment-api minReplicas is not 1"
  for d in "platform-api $P_OLD" "talent-api $T_OLD" "talent-api $TM_OLD"; do manifest_ok $d || stop "rollback image $d missing"; done
  for c in "platform-api $P_SHA" "talent-api $T_SHA"; do set -- $c
    [ -z "$(az acr manifest list-metadata -r $R -n dijione/$1 --query "[?tags && contains(tags, '$2')].digest" -o tsv)" ] || stop "tag dijione/$1:$2 already exists"
    git -C "$ROOT" cat-file -e "$2^{commit}" || stop "commit $2 not available locally"
    [ "$(git -C "$ROOT" ls-remote origin | grep -c "$2")" -ge 1 ] || stop "commit $2 not on any pushed branch"; done
  [ "$(git -C "$ROOT" diff --name-only bed6fb7 $P_SHA | wc -l)" = 8 ] || stop "Platform candidate is not exactly the 8 approved files"
  [ -z "$(git -C "$ROOT" diff --name-only 2a25f93 $T_SHA | grep -v '^apps/talent-api/\|^docs/platform/recruitment-source.md$')" ] || stop "Talent candidate changes files outside talent-api"
  [ -z "$(git -C "$ROOT" show $T_SHA:apps/talent-api/app/services/audit_outbox_service.py $T_SHA:apps/talent-api/scripts/drain_audit_outbox.py | grep -E '^(from|import) .*(recruit|reconcil)')" ] || stop "drain code imports recruitment/reconcile"
  for a in platform-api talent-api $UNTOUCHED_APPS; do app_json $a > "$ST/$a.before.json"; done
  for j in migrate-platform-api migrate-talent-api $UNTOUCHED_JOBS; do job_json $j > "$ST/$j.before.json"; done
  [ "$(az postgres flexible-server show -g $G -n $PG --query state -o tsv | tr -d '\r')" = Ready ] || stop "PostgreSQL server not Ready"
  az postgres flexible-server show -g $G -n $PG --query "{earliest:backup.earliestRestoreDate,days:backup.backupRetentionDays}" -o json > "$ST/pg.recovery.json"
  rm -f "$ST/platform.maxid"; snap_platform baseline
  py -c "import json;print(json.load(open(r'$ST/platform.baseline.json'))['baseline_max_id'])" > "$ST/platform.maxid"
  py "$H/gate.py" platform-baseline-head "a['heads']==['$P_HEAD_OLD'] and a['event_id_column']==0" "$ST/platform.baseline.json"
  snap_talent baseline
  py "$H/gate.py" talent-baseline-head "a['head']=='$T_HEAD_OLD' and not a['outbox_table']" "$ST/talent.baseline.json"
  date -u +%s > "$ST/preflight.time"; ok preflight ;;

p1-protect)  # Rollback images locked against deletion; on-demand DB backup completed.
  need preflight; [ $(( $(date -u +%s) - $(cat "$ST/preflight.time") )) -lt 7200 ] || stop "preflight older than 2 h; re-run it"; guard
  for d in "platform-api $P_OLD" "talent-api $T_OLD" "talent-api $TM_OLD"; do set -- $d
    az acr repository update -n $R --image "dijione/$1@$2" --delete-enabled false -o none
    [ "$(az acr manifest show-metadata -r $R -n dijione/$1@$2 --query changeableAttributes.deleteEnabled -o tsv | tr -d '\r')" = false ] || stop "lock failed on $1@$2"; done
  # PITR safeguards (approved substitute for an on-demand backup, which Burstable servers cannot take).
  # A recorded timestamp is a recovery target, not a new backup.
  pitr_check p1
  py - "$ST" <<'PY'
import json, sys
st = sys.argv[1]
rec = {"server": json.load(open(f"{st}/pg.server.json"))["id"], "pitr": json.load(open(f"{st}/pitr.p1.json")),
       "sources": {"platform-api": "6f2d6be81eff6ed6724bc5d798e400d4923ea86a", "talent-api": "9b35f43f185aaeda53677d229aa1d7cfb331ae30"},
       "rollback_images": {"platform-api": "sha256:a58d2cb14d425a62e9e9896a86fa0ab01ca59efda640f269237db238a0d049c7",
                           "talent-api": "sha256:c146a57ed6a0b77ef67340b972e3d3dd999dd9a8905ec8491d44a72f04ee810d",
                           "migrate-talent-api": "sha256:ad5776134a1af26c05bdfc65240a5de6839dc12be10ffc9e80ee94fc46e2919b"},
       "baseline": {"platform": json.load(open(f"{st}/platform.baseline.json")), "talent": json.load(open(f"{st}/talent.baseline.json"))},
       "restore": "Not automatic. Needs explicit approval: az postgres flexible-server restore -g rg-dijione-dev "
                  "--name <new-server> --source-server psql-dijione-dev --restore-time <recovery_point>. Creates a separate "
                  "server; any connection switch is a separate, authorized change."}
json.dump(rec, open(f"{st}/recovery-record.json", "w"), indent=1)
print("recovery record written")
PY
  ok p1-protect ;;

p2-build)    # Immutable images from clean checkouts of the approved commits, verified file-by-file.
  need p1-protect; guard
  for c in "platform-api $P_SHA" "talent-api $T_SHA"; do set -- $c; w="$ST/src-$1"; rm -rf "$w"
    git -C "$ROOT" worktree add -q --detach "$w" "$2"
    [ "$(git -C "$w" rev-parse HEAD)" = "$2" ] && [ -z "$(git -C "$w" status --porcelain)" ] || stop "$1 checkout not clean at $2"
    az acr build -r $R -f "$w/deploy/Dockerfile.api" --build-arg SERVICE=$1 -t "dijione/$1:$2" "$w" --no-logs -o none
    git -C "$ROOT" worktree remove --force "$w"
    d=$(az acr manifest show-metadata -r $R -n "dijione/$1:$2" --query digest -o tsv | tr -d '\r'); [[ $d == sha256:* ]] || stop "no digest for $1"
    py "$H/imgverify.py" "$ROOT" "$1" "$d" "$2" | tee "$ST/$1.imgverify.json" || stop "$1 image does not match $2"
    az acr repository update -n $R --image "dijione/$1@$d" --delete-enabled false --write-enabled false -o none
    echo "$d" > "$ST/$1.digest"; log "$1 $2 -> $d (verified, locked)"; done
  ok p2-build ;;

p3-platform-migrate)   # o5p6q7r8s9t0 -> a7e1d0c4b9f2 (additive)
  need p2-build; guard; D=$(cat "$ST/platform-api.digest")
  az containerapp job update -g $G -n migrate-platform-api --image "$A/platform-api@$D" -o none
  [ "$(image_of migrate-platform-api job)" = "$A/platform-api@$D" ] || stop "migrate job image not updated"
  cfg_same job migrate-platform-api --allow-image
  pitr_check before-platform-migration
  E=$(az containerapp job start -g $G -n migrate-platform-api --query name -o tsv | tr -d '\r'); wait_exec migrate-platform-api "$E" 960
  snap_platform after-migrate
  py "$H/gate.py" platform-head "a['heads']==['$P_HEAD_NEW'] and a['event_id_column']==1 and a['event_id_unique']==1 and a['audit_rows']>=$(py -c "import json;print(json.load(open(r'$ST/platform.baseline.json'))['audit_rows'])")" "$ST/platform.after-migrate.json"
  platform_unchanged after-migrate; guard; ok p3-platform-migrate ;;

p4-platform-api)
  need p3-platform-migrate; guard; D=$(cat "$ST/platform-api.digest")
  [ "$(image_of platform-api)" = "$A/platform-api@$D" ] || az containerapp update -g $G -n platform-api --image "$A/platform-api@$D" -o none
  wait_rev platform-api "$D"; cfg_same app platform-api --allow-image
  snap_platform after-api; platform_unchanged after-api; guard; ok p4-platform-api ;;

p5-platform-verify)   # Synthetic contract checks through the internal network
  need p4-platform-api; guard; echo "r$(date -u +%Y%m%d%H%M%S)" > "$ST/run.id"
  inapp talent-api in_talent_probe_platform.py PROBE "$ST/probe.json"
  py "$H/gate.py" platform-contract "a['ok']" "$ST/probe.json"
  snap_platform after-probe
  py "$H/gate.py" platform-synthetic-rows "a['synthetic_run_rows']==2 and a['synthetic_run_with_event_id']==1" "$ST/platform.after-probe.json"
  platform_unchanged after-probe; guard; ok p5-platform-verify ;;

p6-talent-migrate)    # b3c5d7e9f1a2 -> c4d6e8f0a2b3 (one new table)
  need p5-platform-verify; guard; D=$(cat "$ST/talent-api.digest")
  [ "$(image_of migrate-talent-api job)" = "$A/talent-api@$D" ] || az containerapp job update -g $G -n migrate-talent-api --image "$A/talent-api@$D" -o none
  [ "$(image_of migrate-talent-api job)" = "$A/talent-api@$D" ] || stop "migrate job image not updated"
  cfg_same job migrate-talent-api --allow-image
  pitr_check before-talent-migration
  E=$(az containerapp job start -g $G -n migrate-talent-api --query name -o tsv | tr -d '\r'); wait_exec migrate-talent-api "$E" 960
  talent_unchanged after-migrate
  py "$H/gate.py" talent-head "a['head']=='$T_HEAD_NEW' and a['outbox_table'] and a['outbox']==[]" "$ST/talent.after-migrate.json"
  guard; ok p6-talent-migrate ;;

p7-talent-api)        # Resources unchanged (0.25 vCPU / 0.5 GiB), enforced by cfgcmp
  need p6-talent-migrate; guard; D=$(cat "$ST/talent-api.digest")
  [ "$(image_of talent-api)" = "$A/talent-api@$D" ] || az containerapp update -g $G -n talent-api --image "$A/talent-api@$D" -o none
  wait_rev talent-api "$D"; cfg_same app talent-api --allow-image
  talent_unchanged after-api; guard; ok p7-talent-api ;;

p8-outbox-job)        # Created Manual; configuration verified by jobcheck
  need p7-talent-api; guard; D=$(cat "$ST/talent-api.digest")
  ENVID=$(az containerapp show -g $G -n talent-api --query properties.environmentId -o tsv | tr -d '\r')
  UAI=$(az containerapp show -g $G -n talent-api --query "properties.configuration.registries[0].identity" -o tsv | tr -d '\r')
  KV=https://kv-dijione-dev.vault.azure.net/secrets
  az containerapp job create -g $G -n $JOB --environment "$ENVID" \
    --trigger-type Manual --replica-timeout 280 --replica-retry-limit 0 --parallelism 1 --replica-completion-count 1 \
    --image "$A/talent-api@$D" --registry-server $R.azurecr.io --registry-identity "$UAI" --mi-user-assigned "$UAI" \
    --cpu 0.25 --memory 0.5Gi --command "python" --args "-m" "scripts.drain_audit_outbox" \
    --secrets "database-url-talent=keyvaultref:$KV/database-url-talent,identityref:$UAI" \
              "internal-service-secret=keyvaultref:$KV/internal-service-secret,identityref:$UAI" \
    --env-vars APP_ENV=development PLATFORM_API_URL=http://platform-api \
               DATABASE_URL=secretref:database-url-talent INTERNAL_SERVICE_SECRET=secretref:internal-service-secret -o none
  job_json $JOB > "$ST/$JOB.created.json"; app_json talent-api > "$ST/talent-api.now.json"
  py "$H/jobcheck.py" "$ST/$JOB.created.json" "$ST/talent-api.now.json" "$A/talent-api@$D" Manual || stop "$JOB configuration wrong"
  guard; ok p8-outbox-job ;;

p8-verify)            # Revalidate the existing job (no recreation): config, zero executions, unchanged data
  need p7-talent-api; guard; D=$(cat "$ST/talent-api.digest")
  job_json $JOB > "$ST/$JOB.created.json"; app_json talent-api > "$ST/talent-api.now.json"
  py "$H/jobcheck.py" "$ST/$JOB.created.json" "$ST/talent-api.now.json" "$A/talent-api@$D" Manual || stop "$JOB configuration wrong"
  py "$H/cmdfix_diff.py" "$ST/$JOB.before-cmdfix.json" "$ST/$JOB.created.json" || stop "$JOB differs from its pre-fix copy beyond the approved changes"
  inapp talent-api in_talent_modcheck.py MODCHECK "$ST/modcheck.json"; py "$H/gate.py" drain-module-resolves "a['ok']" "$ST/modcheck.json"
  # History must be exactly the one known failed startup (ModuleNotFoundError, 10 Nov 10:34 UTC), nothing else.
  hist=$(az containerapp job execution list -g $G -n $JOB --query "[].join(':',[name,properties.status])" -o tsv | tr -d '\r' | sort | tr '\n' ' ')
  [ "$hist" = "talent-audit-outbox-job-vjuzexw:Failed " ] || stop "$JOB execution history is not exactly the known failed run: '$hist'"
  talent_unchanged after-job; guard; ok p8-outbox-job ;;

p9-test-events)       # 3 synthetic outbox events; genuine Talent data must not change
  need p8-outbox-job; guard
  inapp talent-api in_talent_seed_outbox.py SEED "$ST/seed.json"; py "$H/gate.py" outbox-seeded "a['ok']" "$ST/seed.json"
  talent_unchanged after-seed
  py "$H/gate.py" outbox-only-synthetic "a['outbox_non_synthetic']==0" "$ST/talent.after-seed.json"
  guard; ok p9-test-events ;;

p10-delivery)         # Delivery, deduplication, no re-send, empty backlog
  need p9-test-events; guard
  E=$(az containerapp job start -g $G -n $JOB --query name -o tsv | tr -d '\r'); wait_exec $JOB "$E" 400
  inapp talent-api in_talent_outbox_check.py OUTBOX "$ST/outbox1.json"; py "$H/gate.py" delivered-and-deduplicated "a['ok']" "$ST/outbox1.json"
  snap_platform after-delivery
  py "$H/gate.py" platform-has-each-event-once "a['synthetic_run_rows']==5 and a['synthetic_run_with_event_id']==4" "$ST/platform.after-delivery.json"
  E2=$(az containerapp job start -g $G -n $JOB --query name -o tsv | tr -d '\r'); wait_exec $JOB "$E2" 400
  snap_platform after-second-run
  py "$H/gate.py" second-run-sends-nothing "a['synthetic_run_rows']==5" "$ST/platform.after-second-run.json"
  talent_unchanged after-delivery
  py "$H/gate.py" backlog-empty "a['outbox_claimed']==0 and all(s!='PENDING' and s!='FAILED' for s,_ in a['outbox'])" "$ST/talent.after-delivery.json"
  platform_unchanged after-delivery; guard; ok p10-delivery ;;

p11-schedule)         # Needs its own explicit authorization
  need p10-delivery; guard
  [ "${ACTIVATE_SCHEDULE:-}" = "approved" ] || stop "schedule activation not authorized (set ACTIVATE_SCHEDULE=approved only after approval)"
  # The CLI cannot change a job's trigger type; ARM PATCH does. If Azure refuses it,
  # this phase stops: recreating the job as Schedule needs separate approval.
  printf '%s' '{"properties":{"configuration":{"triggerType":"Schedule","manualTriggerConfig":null,"scheduleTriggerConfig":{"cronExpression":"*/5 * * * *","parallelism":1,"replicaCompletionCount":1}}}}' > "$ST/schedule.patch.json"
  need a-cold; job_json $JOB > "$ST/$JOB.before-schedule.json"
  az rest --method patch --url "$(job_url)?api-version=2025-10-02-preview" --body "@$ST/schedule.patch.json" -o none || stop "trigger change refused"
  for i in $(seq 1 30); do [ "$(az containerapp job show -g $G -n $JOB --query properties.provisioningState -o tsv | tr -d '\r')" = Succeeded ] && break; sleep 10; done
  job_json $JOB > "$ST/$JOB.scheduled.json"; app_json talent-api > "$ST/talent-api.now.json"
  py "$H/jobcheck.py" "$ST/$JOB.scheduled.json" "$ST/talent-api.now.json" "$A/talent-api@$(cat "$ST/talent-api2.digest")" Schedule || stop "$JOB schedule configuration wrong"
  date -u +%FT%TZ > "$ST/schedule.start"; guard; ok p11-schedule ;;

p12-monitor)          # 3 scheduled executions, then full integrity comparison
  need p11-schedule; guard; t=0
  while :; do
    n=$(az containerapp job execution list -g $G -n $JOB --query "length([?properties.startTime>='$(cat "$ST/schedule.start")'])" -o tsv | tr -d '\r')
  bad=$(sched_failed | tr -d '
')
    [ "$bad" = 0 ] || stop "a scheduled $JOB execution did not succeed"
    done_n=$(az containerapp job execution list -g $G -n $JOB --query "length([?properties.startTime>='$(cat "$ST/schedule.start")' && properties.status=='Succeeded'])" -o tsv | tr -d '\r')
    [ "$done_n" -ge 3 ] && break; [ $t -ge 1500 ] && stop "fewer than 3 scheduled runs after 25 min ($n started)"; sleep 60; t=$((t+60)); done
  talent_unchanged final; snap_platform final; platform_unchanged final
  for a in $UNTOUCHED_APPS; do cfg_same app $a; done
  for j in $UNTOUCHED_JOBS; do cfg_same job $j; done
  cfg_same app platform-api --allow-image; cfg_same app talent-api --allow-image
  guard; ok p12-monitor ;;

p10-check)            # READ-ONLY preflight before resuming p10 (11 Nov). Known history: vjuzexw (startup) and 3tc8fgy (cold-start ReadTimeout).
  need p9-test-events; guard
  for a in "platform-api platform-api--0000024 $(cat "$ST/platform-api.digest")" "talent-api talent-api--0000016 $(cat "$ST/talent-api.digest")"; do set -- $a
    [ "$(image_of $1)" = "$A/$1@$3" ] || stop "$1 image changed"
    v=$(az containerapp show -g $G -n $1 --query "[properties.latestRevisionName,properties.latestReadyRevisionName,properties.provisioningState]" -o tsv | tr -d '\r' | tr '\n' ' ')
    [ "$v" = "$2 $2 Succeeded " ] || stop "$1 revision state '$v'"
    [ "$(az containerapp revision show -g $G -n $1 --revision $2 --query properties.healthState -o tsv | tr -d '\r')" = Healthy ] || stop "$1 not Healthy"; done
  [ Schedule = Manual ] || stop "$JOB is not Manual"
  hist=$(az containerapp job execution list -g $G -n $JOB --query "[].join(':',[name,properties.status])" -o tsv | tr -d '\r' | sort | tr '\n' ' ')
  [ "$hist" = "talent-audit-outbox-job-3tc8fgy:Failed talent-audit-outbox-job-vjuzexw:Failed " ] || stop "$JOB history is not the two known runs: '$hist'"
  talent_unchanged before-retry
  py "$H/gate.py" talent-head-unchanged "a['head']=='$T_HEAD_NEW'" "$ST/talent.before-retry.json"
  snap_platform before-retry; platform_unchanged before-retry
  py "$H/gate.py" platform-before-retry "a['heads']==['$P_HEAD_NEW'] and a['synthetic_run_rows']==5 and a['synthetic_run_with_event_id']==4 and a['audit_rows']==443" "$ST/platform.before-retry.json"
  inapp talent-api in_talent_event_ids.py EVIDS "$ST/evids.before-retry.json"
  inapp platform-api in_platform_event_ids.py PEVIDS "$ST/pevids.before-retry.json"
  py - "$ST" <<'PY' || stop "pending event or event IDs not as last recorded"
import json, sys
st = sys.argv[1]; t = json.load(open(f"{st}/evids.before-retry.json")); p = json.load(open(f"{st}/pevids.before-retry.json"))["counts"]
r = t["rows"]; ids = [x[2] for x in r]
c = {"three_rows": len(r) == 3, "no_other_outbox_rows": t["non_synthetic"] == 0,
     "row1_pending_unclaimed": r[0][1] == "PENDING" and r[0][4] is False and r[0][5] == "ReadTimeout",
     "rows2_3_delivered": [x[1] for x in r[1:]] == ["DELIVERED", "DELIVERED"] and not any(x[4] for x in r),
     "platform_has_each_once": all(p.get(i) == 1 for i in ids), "platform_has_no_others_from_outbox": len(p) == 4 and set(ids) <= set(p)}
print("PRE " + json.dumps({"ok": all(c.values()), **c})); sys.exit(0 if all(c.values()) else 1)
PY
  date -u +%s > "$ST/p10check.time"; guard; log "p10-check passed" ;;

p10-resume)           # One manual run for the pending event, then the remaining p10 gates. Stops on any failure.
  need p9-test-events; [ $(( $(date -u +%s) - $(cat "$ST/p10check.time") )) -lt 1800 ] || stop "p10-check older than 30 min"; guard
  wake platform-api   # same read-only GET the runbook uses for snapshots; the fix for cold starts is in #90, not deployed
  E=$(az containerapp job start -g $G -n $JOB --query name -o tsv | tr -d '\r'); echo "$E" > "$ST/p10.retry.exec"; log "retry execution $E"; wait_exec $JOB "$E" 400
  inapp talent-api in_talent_outbox_check.py OUTBOX "$ST/outbox1.json"; py "$H/gate.py" delivered-and-deduplicated "a['ok']" "$ST/outbox1.json"
  inapp talent-api in_talent_event_ids.py EVIDS "$ST/evids.after-retry.json"
  inapp platform-api in_platform_event_ids.py PEVIDS "$ST/pevids.after-retry.json"
  py - "$ST" <<'PY' || stop "event IDs not preserved or not recorded exactly once"
import json, sys
st = sys.argv[1]; b = json.load(open(f"{st}/evids.before-retry.json"))["rows"]; a = json.load(open(f"{st}/evids.after-retry.json"))["rows"]
pb = json.load(open(f"{st}/pevids.before-retry.json"))["counts"]; pa = json.load(open(f"{st}/pevids.after-retry.json"))["counts"]
c = {"same_event_ids": [x[2] for x in a] == [x[2] for x in b], "all_delivered_unclaimed": all(x[1] == "DELIVERED" and not x[4] for x in a),
     "platform_counts_unchanged": pa == pb, "each_once": all(pa[x[2]] == 1 for x in a)}
print("POST " + json.dumps({"ok": all(c.values()), **c})); sys.exit(0 if all(c.values()) else 1)
PY
  snap_platform after-delivery
  py "$H/gate.py" platform-has-each-event-once "a['synthetic_run_rows']==5 and a['synthetic_run_with_event_id']==4 and a['audit_rows']==443" "$ST/platform.after-delivery.json"
  E2=$(az containerapp job start -g $G -n $JOB --query name -o tsv | tr -d '\r'); echo "$E2" > "$ST/p10.second.exec"; log "second execution $E2"; wait_exec $JOB "$E2" 400
  snap_platform after-second-run
  py "$H/gate.py" second-run-sends-nothing "a['synthetic_run_rows']==5 and a['audit_rows']==443" "$ST/platform.after-second-run.json"
  talent_unchanged after-delivery
  py "$H/gate.py" backlog-empty "a['outbox_claimed']==0 and all(s!='PENDING' and s!='FAILED' for s,_ in a['outbox'])" "$ST/talent.after-delivery.json"
  platform_unchanged after-second-run; guard; ok p10-delivery ;;

# ---- Phase A (11 Nov standing authorization): cold-start fix cc678fe -> talent-api and the audit job ----
a-preflight)          # READ-ONLY
  need p10-delivery; guard; T2=cc678fe8d304646cd31e7349c84e2c60cf29262d; TC=$(cat "$ST/talent-api.digest")
  [ "$(image_of talent-api)" = "$A/talent-api@$TC" ] || stop "talent-api is not on the p7 image"
  [ "$(image_of $JOB job)" = "$A/talent-api@$TC" ] || stop "$JOB is not on the p7 image"
  [ "$(image_of platform-api)" = "$A/platform-api@$(cat "$ST/platform-api.digest")" ] || stop "platform-api changed"
  [ "$(az containerapp job show -g $G -n $JOB --query properties.configuration.triggerType -o tsv | tr -d '\r')" = Manual ] || stop "$JOB not Manual"
  [ "$(az containerapp job execution list -g $G -n $JOB --query "length([?properties.status=='Running'])" -o tsv | tr -d '\r')" = 0 ] || stop "$JOB running"
  git -C "$ROOT" fetch -q origin feat/talent-audit-outbox
  [ "$(git -C "$ROOT" rev-parse origin/feat/talent-audit-outbox)" = "$T2" ] || stop "PR #90 head is not $T2"
  [ "$(git -C "$ROOT" diff --name-only $T_SHA $T2 | grep -v '^apps/talent-api/\(app/services/audit_outbox_service.py\|scripts/drain_audit_outbox.py\|tests/\)')" = "" ] || stop "commit changes files beyond the approved fix"
  [ -z "$(git -C "$ROOT" diff --name-only $T_SHA $T2 -- apps/talent-api/alembic)" ] || stop "commit changes migrations"
  [ "$(az acr manifest show-metadata -r $R -n dijione/talent-api@$TC --query changeableAttributes.deleteEnabled -o tsv | tr -d '\r')" = false ] || stop "rollback image $TC not locked"
  app_json talent-api > "$ST/talent-api.before.json"; job_json $JOB > "$ST/$JOB.before.json"
  pitr_check phaseA; talent_unchanged phaseA-pre
  py "$H/gate.py" talent-head "a['head']=='$T_HEAD_NEW' and a['outbox_claimed']==0 and all(s=='DELIVERED' for s,_ in a['outbox'])" "$ST/talent.phaseA-pre.json"
  snap_platform phaseA-pre; platform_unchanged phaseA-pre
  py "$H/gate.py" platform-head "a['heads']==['$P_HEAD_NEW'] and a['audit_rows']==443" "$ST/platform.phaseA-pre.json"
  date -u +%s > "$ST/apre.time"; guard; ok a-preflight ;;

a-build)
  need a-preflight; guard; T2=${T2:-cc678fe8d304646cd31e7349c84e2c60cf29262d}; DG=${DG:-talent-api2}; w="$ST/src-talent2"; rm -rf "$w"
  [ -z "$(az acr manifest list-metadata -r $R -n dijione/talent-api --query "[?tags && contains(tags, '$T2')].digest" -o tsv)" ] || stop "tag $T2 exists"
  git -C "$ROOT" worktree add -q --detach "$w" "$T2"
  [ "$(git -C "$w" rev-parse HEAD)" = "$T2" ] && [ -z "$(git -C "$w" status --porcelain)" ] || stop "checkout not clean"
  az acr build -r $R -f "$w/deploy/Dockerfile.api" --build-arg SERVICE=talent-api -t "dijione/talent-api:$T2" "$w" --no-logs -o none
  git -C "$ROOT" worktree remove --force "$w"
  d=$(az acr manifest show-metadata -r $R -n "dijione/talent-api:$T2" --query digest -o tsv | tr -d '\r'); [[ $d == sha256:* ]] || stop "no digest"
  py "$H/imgverify.py" "$ROOT" talent-api "$d" "$T2" | tee "$ST/$DG.imgverify.json" || stop "image does not match $T2"
  az acr repository update -n $R --image "dijione/talent-api@$d" --delete-enabled false --write-enabled false -o none
  echo "$d" > "$ST/$DG.digest"; log "talent-api $T2 -> $d (verified, locked)"; ok a-build ;;

a-deploy)
  need a-build; guard; D=$(cat "$ST/${DG:-talent-api2}.digest")
  [ "$(image_of talent-api)" = "$A/talent-api@$D" ] || az containerapp update -g $G -n talent-api --image "$A/talent-api@$D" -o none
  wait_rev talent-api "$D"; cfg_same app talent-api --allow-image
  # Job: image only, through ARM (the CLI rewrote env entries on migrate-talent-api earlier).
  job_json $JOB | py -c "import json,sys;j=json.load(sys.stdin);c=j['properties']['template']['containers'];c[0]['image']='$A/talent-api@$D';print(json.dumps({'properties':{'template':{'containers':c,'initContainers':None,'volumes':None}}}))" > "$ST/a-job.patch.json"
  az rest --method patch --url "$(job_url)?api-version=2025-10-02-preview" --body "@$ST/a-job.patch.json" -o none || stop "job image update refused"
  for i in $(seq 1 30); do [ "$(az containerapp job show -g $G -n $JOB --query properties.provisioningState -o tsv | tr -d '\r')" = Succeeded ] && break; sleep 10; done
  [ "$(image_of $JOB job)" = "$A/talent-api@$D" ] || stop "job image not updated"
  job_json $JOB > "$ST/$JOB.after.json"; py "$H/cmdfix_diff.py" "$ST/$JOB.before.json" "$ST/$JOB.after.json" --image-only || stop "$JOB changed beyond its image"
  app_json talent-api > "$ST/talent-api.now.json"
  py "$H/jobcheck.py" "$ST/$JOB.after.json" "$ST/talent-api.now.json" "$A/talent-api@$D" "$(az containerapp job show -g $G -n $JOB --query properties.configuration.triggerType -o tsv | tr -d '
')" || stop "$JOB configuration wrong"
  inapp talent-api in_talent_modcheck.py MODCHECK "$ST/modcheck2.json"; py "$H/gate.py" drain-module-resolves "a['ok']" "$ST/modcheck2.json"
  talent_unchanged after-a-deploy; guard; ok a-deploy ;;

a-seed)               # 3 synthetic events under a new run id (previous run kept as run1.id)
  need a-deploy; guard; [ -f "$ST/run1.id" ] || cp "$ST/run.id" "$ST/run1.id"; echo "r$(date -u +%Y%m%d%H%M%S)c" > "$ST/run.id"
  inapp talent-api in_talent_seed_outbox.py SEED "$ST/seed2.json"; py "$H/gate.py" outbox-seeded "a['ok']" "$ST/seed2.json"
  talent_unchanged after-seed2; guard; ok a-seed ;;

a-cold)               # Platform must be at zero replicas; start the drain WITHOUT waking it
  need a-seed; guard; t=0
  until [ "$(az containerapp replica list -g $G -n platform-api --query 'length(@)' -o tsv 2>/dev/null | tr -d '\r')" = 0 ]; do
    [ $t -ge 2400 ] && stop "platform-api did not scale to zero in 40 min"; sleep 30; t=$((t+30)); done
  log "platform-api at 0 replicas"; date -u +%FT%TZ > "$ST/cold.start"
  E=$(az containerapp job start -g $G -n $JOB --query name -o tsv | tr -d '\r'); echo "$E" > "$ST/cold.exec"; log "cold execution $E"; wait_exec $JOB "$E" 400
  inapp talent-api in_talent_event_ids.py EVIDS "$ST/evids.cold.json"
  inapp platform-api in_platform_event_ids.py PEVIDS "$ST/pevids.cold.json"
  py - "$ST" <<'PY' || stop "cold-start delivery not exact"
import json, sys
st = sys.argv[1]; r = json.load(open(f"{st}/evids.cold.json"))["rows"]; p = json.load(open(f"{st}/pevids.cold.json"))["counts"]
c = {"three": len(r) == 3, "delivered_first_attempt": all(x[1] == "DELIVERED" and x[3] == 1 and not x[4] and x[5] is None for x in r),
     "platform_each_once": len(p) == 3 and all(p.get(x[2]) == 1 for x in r)}
print("COLD " + json.dumps({"ok": all(c.values()), **c})); sys.exit(0 if all(c.values()) else 1)
PY
  snap_platform after-cold; platform_unchanged after-cold
  py "$H/gate.py" platform-rows "a['audit_rows']==446 and a['synthetic_run_rows']==3" "$ST/platform.after-cold.json"
  inapp talent-api in_talent_outbox_check.py OUTBOX "$ST/outbox-cold.json"; py "$H/gate.py" resend-duplicate "a['ok']" "$ST/outbox-cold.json"
  E2=$(az containerapp job start -g $G -n $JOB --query name -o tsv | tr -d '\r'); echo "$E2" > "$ST/cold2.exec"; wait_exec $JOB "$E2" 400
  snap_platform after-cold2; py "$H/gate.py" second-run-nothing "a['audit_rows']==446" "$ST/platform.after-cold2.json"
  talent_unchanged after-cold
  py "$H/gate.py" backlog-empty "a['outbox_claimed']==0 and all(s=='DELIVERED' for s,_ in a['outbox'])" "$ST/talent.after-cold.json"
  guard; ok a-cold ;;

# ---- Phase C: first controlled Stage C2 reconcile (11 Nov standing authorization) ----
c2-preflight)         # Read-only apart from a rehearsal inside a transaction that is always rolled back
  need p12-monitor; guard
  [ "$(az containerapp job execution list -g $G -n recruitment-sync-job --query "length([?properties.status=='Running'||properties.status=='Processing'])" -o tsv | tr -d '\r')" = 0 ] || stop "recruitment sync running"
  [ "$(az containerapp show -g $G -n recruitment-api --query properties.template.scale.minReplicas -o tsv | tr -d '\r')" = 1 ] || stop "recruitment-api minReplicas not 1"
  [ "$(image_of talent-api)" = "$A/talent-api@$(cat "$ST/talent-api2.digest")" ] || stop "talent-api image changed"
  bad=$(sched_failed | tr -d '
')
  [ "$bad" = 0 ] || stop "a scheduled audit drain failed"
  pitr_check c2
  inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.before.json"
  py "$H/gate.py" c2-baseline "a['read_only']=='on' and a['head']=='$T_HEAD_NEW' and a['dup_candidate_request']==0 and a['dup_lever_opportunity']==0 and a['dup_lever_candidate']==0 and a['cross_client_requests']==0 and a['apps_on_unverified']==0 and a['requests_per_posting_gt1']==0 and a['visible_apps']==0 and a['magic_link_grants']==0 and a['outbox_claimed']==0 and all(s=='DELIVERED' for s,_ in a['outbox']) and sum(n for s,_,n in a['map_status_source'] if s=='VERIFIED')==33" "$ST/c2.before.json"
  c2_detached rehearsal "$ST/c2.rehearsal.json"
  inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.after-rehearsal.json"
  py "$H/gate.py" rehearsal-left-nothing "a==b" "$ST/c2.before.json" "$ST/c2.after-rehearsal.json"
  py - "$ST" <<'PY' || stop "rehearsal does not meet the C2 acceptance criteria"
import json, sys
st = sys.argv[1]; r = json.load(open(f"{st}/c2.rehearsal.json"))
res = r.get("result") or {}; p = res.get("promotion") or {}; up = r.get("upstream") or {}
tm = r.get("timing") or {}; nv = r.get("newly_verified") or []
c = {"source_complete": up.get("state") == "COMPLETE" and "hold" not in r, "outcome_succeeded": (r.get("outcome") or [None])[0] == "SUCCEEDED",
     "refreshed": res.get("refreshed") is True, "no_reassign_or_revert": res.get("reassigned") == 0 and res.get("reverted") == 0,
     "no_conflicts": res.get("conflicts") == 0 and res.get("ambiguous") == 0, "side_effects_none_delivered": True,
     "existing_verified_untouched": r.get("lost_verified") == [] and r.get("changed_verified") == [],
     "new_mappings_follow_rule": all(x["now"][1] == "LEVER_DTC_TAG" and (x["tag"] or "").startswith("DTC - ") and x["clients_matching_tag_name"] == 1
                                     and x["client"] and (x["prior"] is None or (x["prior"][1] != "MANUAL" and x["prior"][2] != "REJECTED")) for x in nv),
     "verified_count_consistent": r.get("verified_after") == r.get("verified_before", -1) + len(nv) == p.get("verified_postings"),
     "processing_under_180": tm.get("reconcile_processing_s", 999) < 180, "total_under_200": tm.get("total_wall_clock_s", 999) < 200,
     "memory_ok": r.get("maxrss_mb", 9999) < 700}
print("C2_ACCEPT " + json.dumps({"ok": all(c.values()), **c, "timing": tm, "newly_verified": nv, "maxrss_mb": r.get("maxrss_mb"),
      "counts": {k: v for k, v in res.items() if k != "promotion"}, "promotion": p}))
sys.exit(0 if all(c.values()) else 1)
PY
  date -u +%s > "$ST/c2pre.time"; guard; ok c2-preflight ;;

cap-up)               # Temporary 0.5 vCPU / 1 GiB for talent-api (approved 11 Nov); image and all else preserved
  need p12-monitor; guard; D=$(cat "$ST/talent-api2.digest")
  [ "$(image_of talent-api)" = "$A/talent-api@$D" ] || stop "talent-api image is not $D"
  for a in platform-api talent-api; do r=$(az containerapp show -g $G -n $a --query properties.latestRevisionName -o tsv | tr -d '\r')
    [ "$(az containerapp revision show -g $G -n $a --revision $r --query properties.healthState -o tsv | tr -d '\r')" = Healthy ] || stop "$a not Healthy"; done
  [ "$(sched_failed | tr -d '
')" = 0 ] || stop "a scheduled audit drain failed"
  [ "$(az acr manifest show-metadata -r $R -n dijione/talent-api@$(cat "$ST/talent-api.digest") --query changeableAttributes.deleteEnabled -o tsv | tr -d '\r')" = false ] || stop "rollback image not locked"
  pitr_check cap-up; inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.cap-before.json"
  py "$H/gate.py" unchanged-since-c2-baseline "all(a[k]==b[k] for k in a)" "$ST/c2.before.json" "$ST/c2.cap-before.json"
  snap_platform cap-before; platform_unchanged cap-before
  app_json talent-api > "$ST/talent-api.cap-before.json"; cp "$ST/talent-api.cap-before.json" "$ST/talent-api.before.json"
  az containerapp update -g $G -n talent-api --cpu 0.5 --memory 1Gi -o none
  wait_rev talent-api "$D"; app_json talent-api > "$ST/talent-api.cap-up.json"
  py "$H/cfgcmp.py" "$ST/talent-api.cap-before.json" "$ST/talent-api.cap-up.json" --resources=0.5,1Gi || stop "talent-api changed beyond the approved capacity"
  rm -f "$ST/c2.spawn.rehearsal.json"; guard; ok cap-up ;;

cap-down)             # Restore 0.25 vCPU / 0.5 GiB; everything must then match the pre-increase copy exactly
  need cap-up; guard; D=$(cat "$ST/talent-api2.digest")
  az containerapp update -g $G -n talent-api --cpu 0.25 --memory 0.5Gi -o none
  wait_rev talent-api "$D"; app_json talent-api > "$ST/talent-api.cap-down.json"
  py "$H/cfgcmp.py" "$ST/talent-api.cap-before.json" "$ST/talent-api.cap-down.json" || stop "talent-api not restored exactly"
  inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.final.json"
  py "$H/gate.py" final-isolation "a['dup_candidate_request']==0 and a['dup_lever_opportunity']==0 and a['dup_lever_candidate']==0 and a['cross_client_requests']==0 and a['apps_on_unverified']==0 and a['visible_apps']==0 and a['magic_link_grants']==0 and a['outbox_claimed']==0" "$ST/c2.final.json"
  snap_platform final2; platform_unchanged final2; guard; ok cap-down ;;

c2-run)               # One reconcile through the internal route, then integrity, delivery and idempotency gates
  need c2-preflight; [ $(( $(date -u +%s) - $(cat "$ST/c2pre.time") )) -lt 1800 ] || stop "c2-preflight older than 30 min"; guard
  c2_detached run "$ST/c2.run.json"
  py "$H/gate.py" c2-succeeded "a.get('http')==200 and a['body']['outcome']=='SUCCEEDED'" "$ST/c2.run.json"
  inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.after.json"
  py - "$ST" <<'PY' || stop "post-reconcile integrity gate failed"
import json, sys
st = sys.argv[1]; b = json.load(open(f"{st}/c2.before.json")); a = json.load(open(f"{st}/c2.after.json"))
p = json.load(open(f"{st}/c2.run.json"))["body"]["counts"]["promotion"]
c = {k: a[k] == 0 for k in ("dup_candidate_request", "dup_lever_opportunity", "dup_lever_candidate", "cross_client_requests", "apps_on_unverified",
                              "requests_per_posting_gt1", "visible_apps", "magic_link_grants")}
nv = {x["posting_external_id"]: x["now"][0] for x in json.load(open(f"{st}/c2.rehearsal.json"))["newly_verified"]}
c["verified_is_before_plus_approved"] = sorted(map(tuple, a["verified_ids"])) == sorted([tuple(x) for x in b["verified_ids"]] + [(k, v, "LEVER_DTC_TAG") for k, v in nv.items()])
c |= {k: a[k] == b[k] for k in ("client_hash", "grant_hash", "clients", "magic_link_grants", "interviews", "messages", "documents")}
c["applications_add_up"] = a["applications"] == b["applications"] + p["applications_created"]
c["candidates_add_up"] = a["candidates"] == b["candidates"] + p["candidates_created"]
c["requests_add_up"] = a["talent_requests"] == b["talent_requests"] + p["talent_requests_created"]
print("C2_INTEGRITY " + json.dumps({"ok": all(c.values()), "failed": [k for k, v in c.items() if not v]})); sys.exit(0 if all(c.values()) else 1)
PY
  t=0; until inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.drained.json" && py "$H/gate.py" audit-drained "a['outbox_claimed']==0 and all(s=='DELIVERED' for s,_ in a['outbox'])" "$ST/c2.drained.json"; do
    log "backlog: $(py -c "import json;a=json.load(open(r'$ST/c2.drained.json'));print(a['outbox'],'claimed',a['outbox_claimed'])")"
    [ $t -ge 5400 ] && stop "reconcile audit events not drained after 90 min"; sleep 300; t=$((t+300)); done
  snap_platform after-c2; platform_unchanged after-c2
  py "$H/gate.py" platform-has-reconcile-events "a['audit_rows']-446>=b['outbox_reconcile']" "$ST/platform.after-c2.json" "$ST/c2.drained.json"
  py "$H/gate.py" data-stable-while-draining "{k:v for k,v in a.items() if not k.startswith('outbox')}=={k:v for k,v in b.items() if not k.startswith('outbox')}" "$ST/c2.after.json" "$ST/c2.drained.json"
  [ "$(sched_failed | tr -d '
')" = 0 ] || stop "a scheduled audit drain failed during the backlog"
  guard; ok c2-run ;;

c2-check)             # READ-ONLY: integrity snapshot compared with c2.before
  guard; inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.after-rehearsal.json"
  py "$H/gate.py" rehearsal-left-nothing "a==b" "$ST/c2.before.json" "$ST/c2.after-rehearsal.json" ;;

c2-probe)             # harmless execution: proves the per-execution override (prints only)
  c2_detached probe "$ST/c2.probe.json"; cat "$ST/c2.probe.json"; echo; job_json $JOB > "$ST/$JOB.after-probe.json"
  py "$H/cfgcmp.py" "$ST/$JOB.scheduled.json" "$ST/$JOB.after-probe.json" ;;

c2-idem)              # rollback-only rehearsal after C2: proves a re-run creates nothing
  guard; rm -f "$ST/c2.exec.rehearsal"; c2_detached rehearsal "$ST/c2.idem.json"
  inapp talent-api in_talent_c2_integrity.py C2SNAP "$ST/c2.after-idem.json"
  py "$H/gate.py" idem-left-nothing "{k:v for k,v in a.items() if not k.startswith('outbox')}=={k:v for k,v in b.items() if not k.startswith('outbox')}" "$ST/c2.drained.json" "$ST/c2.after-idem.json"
  py -c "import json;r=json.load(open(r'$ST/c2.idem.json'));p=r['result']['promotion'];print('IDEM',json.dumps({'outcome':r['outcome'],'timing':r['timing'],'created':{k:p[k] for k in p if k.endswith('created')},'updated':{k:p[k] for k in p if k.endswith('updated')},'newly_verified':len(r['newly_verified'])}))" ;;

c2-trace)             # READ-ONLY: traceback frames of a detached C2 process ($2 = mode)
  MODE=$2 inapp talent-api in_talent_c2_trace.py TRACE "$ST/c2.trace.$2.json"; cat "$ST/c2.trace.$2.json" ;;

modcheck)             # READ-ONLY: resolve the drain module inside the deployed Talent image
  inapp talent-api in_talent_modcheck.py MODCHECK "$ST/modcheck.json"; py "$H/gate.py" drain-module-resolves "a['ok']" "$ST/modcheck.json" ;;

outbox-rows)          # READ-ONLY: delivery state of the synthetic run rows
  inapp talent-api in_talent_outbox_rows.py ROWS "$ST/outbox-rows.json"; cat "$ST/outbox-rows.json" ;;

snapshot)             # READ-ONLY: snapshot both databases under tag $2 and compare Talent data with baseline
  guard; snap_talent "$2"; snap_platform "$2"; py "$H/gate.py" "talent-data-unchanged-$2" "strip(a)==strip(b)" "$ST/talent.baseline.json" "$ST/talent.$2.json"; platform_unchanged "$2" ;;

rollback)             # Reverse order, each step verified. Schemas stay (additive, ignored by old images).
  guard
  if [ -n "$(az containerapp job list -g $G --query "[?name=='$JOB'].name" -o tsv)" ]; then
    # Same suspend mechanism already used for talent-reconcile-job; the job and its history stay.
    az rest --method post --url "$(job_url)/suspend?api-version=$API" -o none
    for i in $(seq 1 30); do [ "$(az rest --method get --url "$(job_url)?api-version=$API" --query properties.runningState -o tsv | tr -d '\r')" = Suspended ] && break; sleep 10; done
    [ "$(az rest --method get --url "$(job_url)?api-version=$API" --query properties.runningState -o tsv | tr -d '\r')" = Suspended ] || stop "could not suspend $JOB"
    for i in $(seq 1 20); do   # let an in-flight drain finish; its claims expire on their own if not
      [ "$(az containerapp job execution list -g $G -n $JOB --query "length([?properties.status=='Running'])" -o tsv | tr -d '\r')" = 0 ] && break; sleep 15; done; fi
  if [ "$(image_of talent-api)" != "$A/talent-api@$T_OLD" ]; then az containerapp update -g $G -n talent-api --image "$A/talent-api@$T_OLD" -o none; wait_rev talent-api "$T_OLD"; fi
  az containerapp job update -g $G -n migrate-talent-api --image "$A/talent-api@$TM_OLD" -o none
  if [ "$(image_of platform-api)" != "$A/platform-api@$P_OLD" ]; then az containerapp update -g $G -n platform-api --image "$A/platform-api@$P_OLD" -o none; wait_rev platform-api "$P_OLD"; fi
  az containerapp job update -g $G -n migrate-platform-api --image "$A/platform-api@$P_OLD" -o none
  for a in platform-api talent-api; do cfg_same app $a --allow-image; done
  talent_unchanged after-rollback; snap_platform after-rollback; platform_unchanged after-rollback
  log "Rolled back. Undelivered outbox rows kept. No schema downgrade without separate approval."; guard ;;

*) echo "phases: preflight p1-protect p2-build p3-platform-migrate p4-platform-api p5-platform-verify p6-talent-migrate p7-talent-api p8-outbox-job p9-test-events p10-delivery p11-schedule p12-monitor rollback"; exit 2 ;;
esac
