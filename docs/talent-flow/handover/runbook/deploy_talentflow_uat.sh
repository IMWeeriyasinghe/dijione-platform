#!/bin/bash
# DijiTalentFlow V1 UAT rollout (approved 12 Nov). docs/talent-flow/v1-uat-deployment.md.
# Usage: deploy_talentflow_uat.sh <phase>. Each phase checks its gates and stops on failure.
# Database reads run as one-off executions of talent-audit-outbox-job (no container exec).
set -euo pipefail
export MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8 RB_ENV=uat
G=rg-dijione-uat; R=crdijionenonprod; A=$R.azurecr.io/dijione; PG=psql-dijione-uat; JOB=talent-audit-outbox-job
ROOT="C:/Projects/Diji Projects/DijiOne/dijione-platform"
H="$(cygpath -m "$(cd "$(dirname "$0")" && pwd)")/audit-runbook"; ST="$H/state-uat"; mkdir -p "$ST"
SHA=0437a89f723b8ba11981a61f50ff2d8bf96909a1   # PR #92 squash merge into release/onsite-v1 (tree == validated 2bad33c)
PORTAL=https://talentflow-portal-web.mangofield-96838df7.southeastasia.azurecontainerapps.io
P_HEAD=c9d2e4f6a8b1; T_HEAD=c4d6e8f0a2b3
APIS="platform-api talent-api recruitment-api"; WEBS="shell-web talent-web talentflow-portal-web"
ALL_APPS="platform-api talent-api recruitment-api shell-web talent-web talentflow-portal-web"
JOBS="migrate-platform-api migrate-talent-api migrate-recruitment-api recruitment-sync-job talent-reconcile-job bootstrap-talent-clients"
ARMV=2025-10-02-preview

log(){ echo "[$(date -u +%TZ)] $*" | tee -a "$ST/runbook.log"; }
stop(){ log "STOP: $*"; exit 1; }
need(){ for p; do [ -f "$ST/$p.ok" ] || stop "prerequisite '$p' has not completed"; done; }
ok(){ touch "$ST/$1.ok"; log "PHASE $1 COMPLETE"; }
py(){ python "$@"; }
image_of(){ az containerapp ${2:-} show -g $G -n "$1" --query "properties.template.containers[0].image" -o tsv | tr -d '\r'; }
res_url(){ echo "https://management.azure.com$(az containerapp $1 show -g $G -n "$2" --query id -o tsv | tr -d '\r')"; }
dig(){ cat "$ST/$1.digest"; }

wait_exec(){ local job=$1 ex=$2 limit=${3:-1200} t=0 s
  while :; do
    s=$(az containerapp job execution show -g $G -n "$job" --job-execution-name "$ex" --query properties.status -o tsv | tr -d '\r')
    case "$s" in Succeeded) log "$job/$ex Succeeded"; return 0 ;; Failed|Stopped|Degraded|Cancelled|Canceled) stop "$job/$ex ended $s" ;; esac
    [ $t -ge $limit ] && stop "$job/$ex not terminal after ${limit}s"; sleep 15; t=$((t+15)); done; }

wait_rev(){ local app=$1 img=$2 t=0 v latest ready prov cur health traffic
  while :; do
    v=$(az containerapp show -g $G -n "$app" --query "[properties.latestRevisionName,properties.latestReadyRevisionName,properties.provisioningState,properties.template.containers[0].image]" -o tsv | tr -d '\r' | tr '\n' ' ')
    read -r latest ready prov cur <<<"$v" || true
    if [ "$latest" = "$ready" ] && [ "$prov" = Succeeded ] && [ "$cur" = "$img" ]; then
      read -r health traffic < <(az containerapp revision show -g $G -n "$app" --revision "$latest" --query "[properties.healthState,properties.trafficWeight]" -o tsv | tr -d '\r' | tr '\n' ' ') || true
      [ "$health" = Healthy ] && [ "$traffic" = 100 ] && { log "$app $latest Healthy, 100% traffic"; return 0; }
      [ "$health" = Unhealthy ] && stop "$app $latest Unhealthy"; fi
    [ $t -ge 600 ] && stop "$app not Healthy on $img after 600s"; sleep 15; t=$((t+15)); done; }

# `az containerapp update` can add value:"" beside a Key Vault secretRef; put those entries back to secretRef only.
# `az containerapp update` can add or drop value:"" beside a Key Vault secretRef. Put each such entry
# back exactly as it was in the pre-change copy ($ST/$app.pre.json); nothing else is touched.
secretref_fix(){ local app=$1 img=$2
  az containerapp show -g $G -n $app -o json | py -c "
import json,sys;pre={e['name']:e for e in json.load(open(r'$ST/$app.pre.json',encoding='utf-8-sig'))['properties']['template']['containers'][0].get('env') or []}
c=json.load(sys.stdin)['properties']['template']['containers'];n=0
for e in c[0].get('env') or []:
  p=pre.get(e['name'])
  if e.get('secretRef') and p and p.get('secretRef')==e['secretRef'] and ('value' in p)!=('value' in e) and e.get('value','')=='' and p.get('value','')=='':
    e.pop('value',None)
    if 'value' in p: e['value']=''
    n+=1
print(json.dumps({'properties':{'template':{'containers':c}}}) if n else '')" > "$ST/$app.envfix.json"
  [ -s "$ST/$app.envfix.json" ] || return 0
  az rest --method patch --url "$(res_url '' $app)?api-version=$ARMV" --body "@$ST/$app.envfix.json" -o none || { log "$app env fix refused; the strict comparison below decides"; return 0; }
  log "$app: secretRef entries restored to their pre-change form"; sleep 20; wait_rev $app "$img"; }

app_set_image(){ local app=$1 img=$2
  [ -s "$ST/$app.pre.json" ] && [ "$(image_of $app)" = "$img" ] || az containerapp show -g $G -n $app -o json > "$ST/$app.pre.json"
  [ "$(image_of $app)" = "$img" ] || az containerapp update -g $G -n $app --image "$img" -o none
  wait_rev $app "$img"; secretref_fix $app "$img"; az containerapp show -g $G -n $app -o json > "$ST/$app.post.json"
  py "$H/cfgcmp.py" "$ST/$app.pre.json" "$ST/$app.post.json" --allow-image || stop "$app changed beyond its image"; }

# Jobs: image (and optionally args) through ARM; the CLI once rewrote env entries on a job.
job_set_image(){ local job=$1 img=$2 args=${3:-}
  az containerapp job show -g $G -n $job -o json > "$ST/$job.pre.json"
  py - "$ST/$job.pre.json" "$img" "$args" > "$ST/$job.patch.json" <<'PYY'
import json, sys
j = json.load(open(sys.argv[1], encoding="utf-8-sig")); c = j["properties"]["template"]["containers"]
c[0]["image"] = sys.argv[2]
if sys.argv[3]: c[0]["args"] = [sys.argv[3]]
print(json.dumps({"properties": {"template": {"containers": c, "initContainers": None, "volumes": None}}}))
PYY
  az rest --method patch --url "$(res_url job $job)?api-version=$ARMV" --body "@$ST/$job.patch.json" -o none || stop "$job update refused"
  for i in $(seq 1 30); do [ "$(az containerapp job show -g $G -n $job --query properties.provisioningState -o tsv | tr -d '\r')" = Succeeded ] && break; sleep 10; done
  az containerapp job show -g $G -n $job -o json > "$ST/$job.post.json"
  py - "$ST/$job.pre.json" "$ST/$job.post.json" "$img" "$args" <<'PYY' || stop "$job changed beyond its image/args"
import json, sys
def flat(d, p=""):
    if isinstance(d, dict):
        for k, v in d.items(): yield from flat(v, f"{p}.{k}")
    elif isinstance(d, list):
        for i, v in enumerate(d): yield from flat(v, f"{p}[{i}]")
    else: yield p, d
a, b = (dict(flat(json.load(open(f, encoding="utf-8-sig")))) for f in sys.argv[1:3])
C = ".properties.template.containers[0]"
allowed = {C + ".image": sys.argv[3]}
if sys.argv[4]: allowed[C + ".args[0]"] = sys.argv[4]
diff = {k for k in set(a) | set(b) if a.get(k) != b.get(k) and "systemData" not in k and "etag" not in k}
bad = [k for k in diff if k not in allowed and not (k == C + ".resources.ephemeralStorage" and a.get(k) == "" and k not in b)]
ok = not bad and all(b.get(k) == v for k, v in allowed.items())
print("JOBDIFF " + json.dumps({"ok": ok, "changed": sorted(diff), "unexpected": sorted(bad)})); sys.exit(0 if ok else 1)
PYY
  log "$job -> $img"; }

reconcile_guard(){
  [ "$(az containerapp job show -g $G -n talent-reconcile-job --query properties.runningStatus -o tsv | tr -d '\r')" = Suspended ] || stop "talent-reconcile-job is not Suspended"
  [ "$(az containerapp job execution list -g $G -n talent-reconcile-job --query "length([?properties.status=='Running'||properties.status=='Processing'])" -o tsv | tr -d '\r')" = 0 ] || stop "talent-reconcile-job running"; }
no_running(){ local j; for j in "$@"; do
  [ "$(az containerapp job execution list -g $G -n $j --query "length([?properties.status=='Running'||properties.status=='Processing'])" -o tsv | tr -d '\r')" = 0 ] || stop "$j has a running execution"; done; }

# One-off execution of the audit job with a per-execution override; result read from Log Analytics.
jrun(){ local mode=$1 out=$2 E t=0 res="" img; img=$(image_of $JOB job)
  py - "$H/c2_body_$mode.py" "$img" "$JOB" > "$ST/jrun.$mode.yaml" <<'PYY'
import base64, json, sys, zlib
body, img, job = sys.argv[1:4]
code = base64.b64encode(zlib.compress(open(body, "rb").read(), 9)).decode()
env = [{"name": "APP_ENV", "value": "uat"}, {"name": "PLATFORM_API_URL", "value": "http://platform-api"},
       {"name": "RECRUITMENT_API_URL", "value": "http://recruitment-api"}, {"name": "DATABASE_URL", "secretRef": "database-url-talent"},
       {"name": "INTERNAL_SERVICE_SECRET", "secretRef": "internal-service-secret"}, {"name": "C2_CODE", "value": code}]
print(json.dumps({"containers": [{"name": job, "image": img, "command": ["python"],
      "args": ["-c", "import base64,os,zlib;exec(zlib.decompress(base64.b64decode(os.environ['C2_CODE'])))"],
      "env": env, "resources": {"cpu": 0.25, "memory": "0.5Gi"}}]}))
PYY
  E=$(az containerapp job start -g $G -n $JOB --yaml "$ST/jrun.$mode.yaml" --query name -o tsv | tr -d '\r')
  [ -n "$E" ] || stop "$mode execution did not start"; echo "$E" >> "$ST/override.executions"; log "$mode execution $E"
  wait_exec $JOB "$E" 400
  while :; do
    res=$(az monitor log-analytics query -w "$(cat "$ST/ws.id")" --analytics-query "ContainerAppConsoleLogs_CL | where ContainerJobName_s == '$JOB' and ContainerGroupName_s startswith '$E' and Log_s startswith 'C2R ' | top 1 by TimeGenerated | project Log_s" -o tsv 2>/dev/null | head -1 | cut -f1)
    [ -n "$res" ] && break; [ $t -ge 600 ] && stop "$mode result not in logs after 600 s"; sleep 30; t=$((t+30)); done
  printf '%s' "${res#C2R }" | py -c "import json,sys;json.dump(json.loads(sys.stdin.read()),open(r'$out','w'))" || stop "$mode result unreadable"
  log "$mode: $(cut -c1-600 "$out")"; }

mig_log_has(){ az monitor log-analytics query -w "$(cat "$ST/ws.id")" --analytics-query "ContainerAppConsoleLogs_CL | where ContainerJobName_s == '$1' and ContainerGroupName_s startswith '$2' | project Log_s" -o tsv 2>/dev/null | tr -d '\r' > "$ST/$1.$2.log"; }

case "${1:-}" in
pre)        # READ-ONLY: capture, health, PITR point, rollback images present
  rm -f "$ST"/*.ok
  WS=$(az containerapp env show -g $G -n cae-dijione-uat --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId -o tsv | tr -d '\r'); echo "$WS" > "$ST/ws.id"
  for a in $ALL_APPS; do az containerapp show -g $G -n $a -o json > "$ST/$a.before.json"; image_of $a > "$ST/$a.rollback"
    r=$(az containerapp show -g $G -n $a --query properties.latestRevisionName -o tsv | tr -d '\r')
    [ "$(az containerapp revision show -g $G -n $a --revision $r --query properties.healthState -o tsv | tr -d '\r')" = Healthy ] || stop "$a not Healthy"; done
  for j in $JOBS; do az containerapp job show -g $G -n $j -o json > "$ST/$j.before.json"; image_of $j job > "$ST/$j.rollback"; done
  [ -z "$(az containerapp job list -g $G --query "[?name=='$JOB'].name" -o tsv)" ] || stop "$JOB already exists in UAT"
  no_running $JOBS
  az postgres flexible-server show -g $G -n $PG --query "{state:state,earliest:backup.earliestRestoreDate,days:backup.backupRetentionDays}" -o json > "$ST/pitr.pre.json"
  py -c "import json;d=json.load(open(r'$ST/pitr.pre.json'));assert d['state']=='Ready' and d['days']>=7,d"
  date -u +%FT%TZ > "$ST/recovery.point"; log "recovery point $(cat "$ST/recovery.point") (PITR target, not a backup)"
  for a in $ALL_APPS; do log "rollback $a $(cat "$ST/$a.rollback")"; done
  ok pre ;;

lock)       # Rollback images: deletion disabled
  need pre
  for f in "$ST"/*.rollback; do img=$(cat "$f"); n=${img#$A/}; repo=${n%@*}; d=${img#*@}
    az acr repository update -n $R --image "dijione/$repo@$d" --delete-enabled false -o none
    [ "$(az acr manifest show-metadata -r $R -n dijione/$repo@$d --query changeableAttributes.deleteEnabled -o tsv | tr -d '\r')" = false ] || stop "lock failed $repo@$d"; done
  ok lock ;;

build)      # Six images from a clean checkout of $SHA; API images verified file by file; all locked
  need lock; w="$ST/src"; rm -rf "$w"
  git -C "$ROOT" fetch -q origin release/onsite-v1
  [ "$(git -C "$ROOT" rev-parse origin/release/onsite-v1)" = "$SHA" ] || stop "release/onsite-v1 moved past $SHA"
  git -C "$ROOT" worktree add -q --detach "$w" "$SHA"
  [ -z "$(git -C "$w" status --porcelain)" ] || stop "checkout not clean"
  for a in $APIS $WEBS; do
    [ -z "$(az acr manifest list-metadata -r $R -n dijione/$a --query "[?tags && contains(tags, '$SHA')].digest" -o tsv 2>/dev/null)" ] || stop "tag $a:$SHA exists"
    if [[ " $APIS " == *" $a "* ]]; then az acr build -r $R -f "$w/deploy/Dockerfile.api" --build-arg SERVICE=$a -t "dijione/$a:$SHA" "$w" --no-logs -o none
    else az acr build -r $R -f "$w/deploy/Dockerfile.web" --build-arg APP=$a --build-arg GIT_SHA=${SHA:0:7} --build-arg BUILD_DATE=$(date -u +%F) -t "dijione/$a:$SHA" "$w" --no-logs -o none; fi
    d=$(az acr manifest show-metadata -r $R -n "dijione/$a:$SHA" --query digest -o tsv | tr -d '\r'); [[ $d == sha256:* ]] || stop "no digest for $a"
    if [[ " $APIS " == *" $a "* ]]; then py "$H/imgverify.py" "$ROOT" $a "$d" "$SHA" | tee "$ST/$a.imgverify.json" || stop "$a image does not match $SHA"; fi
    az acr repository update -n $R --image "dijione/$a@$d" --delete-enabled false --write-enabled false -o none
    echo "$d" > "$ST/$a.digest"; log "$a $SHA -> $d (locked)"; done
  git -C "$ROOT" worktree remove --force "$w"; ok build ;;

suspend)    # Before any Talent change
  need build; no_running talent-reconcile-job
  az rest --method post --url "$(res_url job talent-reconcile-job)/suspend?api-version=2026-07-01" -o none
  for i in $(seq 1 30); do [ "$(az containerapp job show -g $G -n talent-reconcile-job --query properties.runningStatus -o tsv | tr -d '\r')" = Suspended ] && break; sleep 10; done
  reconcile_guard; ok suspend ;;

audit-job)  # Created Manual, exactly as DEV; used for the read-only snapshots before Talent changes
  need suspend; reconcile_guard
  ENVID=$(az containerapp show -g $G -n talent-api --query properties.environmentId -o tsv | tr -d '\r')
  UAI=$(az containerapp show -g $G -n talent-api --query "properties.configuration.registries[0].identity" -o tsv | tr -d '\r')
  KV=https://kv-dijione-uat.vault.azure.net/secrets
  az containerapp job create -g $G -n $JOB --environment "$ENVID" \
    --trigger-type Manual --replica-timeout 280 --replica-retry-limit 0 --parallelism 1 --replica-completion-count 1 \
    --image "$A/talent-api@$(dig talent-api)" --registry-server $R.azurecr.io --registry-identity "$UAI" --mi-user-assigned "$UAI" \
    --cpu 0.25 --memory 0.5Gi --command "python" --args "scripts/drain_audit_outbox.py" \
    --secrets "database-url-talent=keyvaultref:$KV/database-url-talent,identityref:$UAI" \
              "internal-service-secret=keyvaultref:$KV/internal-service-secret,identityref:$UAI" \
    --env-vars APP_ENV=uat PLATFORM_API_URL=http://platform-api \
               DATABASE_URL=secretref:database-url-talent INTERNAL_SERVICE_SECRET=secretref:internal-service-secret -o none
  # The CLI cannot pass "-m" as an argument; set the approved module command through ARM, as in DEV.
  az containerapp job show -g $G -n $JOB -o json | py -c "import json,sys;j=json.load(sys.stdin);c=j['properties']['template']['containers'];c[0]['args']=['-m','scripts.drain_audit_outbox'];print(json.dumps({'properties':{'template':{'containers':c,'initContainers':None,'volumes':None}}}))" > "$ST/$JOB.args.patch.json"
  az rest --method patch --url "$(res_url job $JOB)?api-version=$ARMV" --body "@$ST/$JOB.args.patch.json" -o none || stop "$JOB args update refused"
  for i in $(seq 1 30); do [ "$(az containerapp job show -g $G -n $JOB --query properties.provisioningState -o tsv | tr -d '\r')" = Succeeded ] && break; sleep 10; done
  az containerapp job show -g $G -n $JOB -o json > "$ST/$JOB.created.json"; az containerapp show -g $G -n talent-api -o json > "$ST/talent-api.now.json"
  py "$H/jobcheck.py" "$ST/$JOB.created.json" "$ST/talent-api.now.json" "$A/talent-api@$(dig talent-api)" Manual || stop "$JOB configuration wrong"
  jrun snap "$ST/talent.before.json"
  py "$H/gate.py" talent-read-only "a['read_only']=='on'" "$ST/talent.before.json"
  ok audit-job ;;

platform)   # migrate-platform-api -> head c9d2e4f6a8b1, then platform-api
  need audit-job; reconcile_guard; no_running migrate-platform-api
  I="$A/platform-api@$(dig platform-api)"; job_set_image migrate-platform-api "$I"
  E=$(az containerapp job start -g $G -n migrate-platform-api --query name -o tsv | tr -d '\r'); log "migrate-platform-api $E"; wait_exec migrate-platform-api "$E" 960
  sleep 90; mig_log_has migrate-platform-api "$E"
  grep -q "Running upgrade .* -> $P_HEAD" "$ST/migrate-platform-api.$E.log" || stop "platform migration log does not show -> $P_HEAD"
  grep -qiE "Traceback|Error" "$ST/migrate-platform-api.$E.log" && stop "platform migration log has errors"
  app_set_image platform-api "$I"; ok platform ;;

recruitment) # migrate-recruitment-api (0003), recruitment-api, recruitment-sync-job (image + documented args)
  need platform; reconcile_guard; no_running migrate-recruitment-api recruitment-sync-job
  I="$A/recruitment-api@$(dig recruitment-api)"; job_set_image migrate-recruitment-api "$I"
  E=$(az containerapp job start -g $G -n migrate-recruitment-api --query name -o tsv | tr -d '\r'); log "migrate-recruitment-api $E"; wait_exec migrate-recruitment-api "$E" 960
  sleep 90; mig_log_has migrate-recruitment-api "$E"; grep -qiE "Traceback|Error" "$ST/migrate-recruitment-api.$E.log" && stop "recruitment migration log has errors"
  app_set_image recruitment-api "$I"
  job_set_image recruitment-sync-job "$I" "python scripts/run_scheduled_sync.py"; ok recruitment ;;

talent)     # migrate-talent-api (audit_outbox), talent-api image, then EXTERNAL_PORTAL_BASE_URL
  need recruitment; reconcile_guard; no_running migrate-talent-api
  I="$A/talent-api@$(dig talent-api)"; job_set_image migrate-talent-api "$I"
  E=$(az containerapp job start -g $G -n migrate-talent-api --query name -o tsv | tr -d '\r'); log "migrate-talent-api $E"; wait_exec migrate-talent-api "$E" 960
  jrun snap "$ST/talent.after-migrate.json"
  py "$H/gate.py" talent-head "a['head']=='$T_HEAD' and a['outbox_table'] and a['outbox']==[]" "$ST/talent.after-migrate.json"
  py "$H/gate.py" talent-data-unchanged "all(a[k]==b[k] for k in a if not k.startswith('outbox') and k!='head')" "$ST/talent.before.json" "$ST/talent.after-migrate.json"
  app_set_image talent-api "$I"
  az containerapp show -g $G -n talent-api -o json > "$ST/talent-api.pre-env.json"
  az containerapp update -g $G -n talent-api --set-env-vars "EXTERNAL_PORTAL_BASE_URL=$PORTAL" -o none
  wait_rev talent-api "$I"; az containerapp show -g $G -n talent-api -o json > "$ST/talent-api.post-env.json"
  py - "$ST/talent-api.pre-env.json" "$ST/talent-api.post-env.json" "$PORTAL" <<'PYY' || stop "talent-api changed beyond EXTERNAL_PORTAL_BASE_URL"
import json, sys
a, b = (json.load(open(f, encoding="utf-8-sig"))["properties"]["template"]["containers"][0] for f in sys.argv[1:3])
ea = {e["name"]: (e.get("value"), e.get("secretRef")) for e in a["env"]}; eb = {e["name"]: (e.get("value"), e.get("secretRef")) for e in b["env"]}
want = dict(ea); want["EXTERNAL_PORTAL_BASE_URL"] = (sys.argv[3], None)
ok = eb == want and a["image"] == b["image"] and a["resources"]["cpu"] == b["resources"]["cpu"] and a["resources"]["memory"] == b["resources"]["memory"]
print("ENVDIFF " + json.dumps({"ok": ok})); sys.exit(0 if ok else 1)
PYY
  ok talent ;;

web)        # shell-web (callback fix), talent-web, portal; shell custom domain must stay bound
  need talent
  az containerapp hostname list -g $G -n shell-web --query "[].name" -o tsv | tr -d '\r' | sort > "$ST/shell.hostnames.before"
  for a in $WEBS; do app_set_image $a "$A/$a@$(dig $a)"; done
  az containerapp hostname list -g $G -n shell-web --query "[].name" -o tsv | tr -d '\r' | sort > "$ST/shell.hostnames.after"
  cmp -s "$ST/shell.hostnames.before" "$ST/shell.hostnames.after" || stop "shell-web hostnames changed"
  ok web ;;

audit-verify) # First manual drain on the new schema (empty outbox), then the five-minute schedule
  need web; reconcile_guard
  E=$(az containerapp job start -g $G -n $JOB --query name -o tsv | tr -d '\r'); wait_exec $JOB "$E" 400
  printf '%s' '{"properties":{"configuration":{"triggerType":"Schedule","manualTriggerConfig":null,"scheduleTriggerConfig":{"cronExpression":"*/5 * * * *","parallelism":1,"replicaCompletionCount":1}}}}' > "$ST/schedule.patch.json"
  az rest --method patch --url "$(res_url job $JOB)?api-version=$ARMV" --body "@$ST/schedule.patch.json" -o none || stop "schedule refused"
  for i in $(seq 1 30); do [ "$(az containerapp job show -g $G -n $JOB --query properties.provisioningState -o tsv | tr -d '\r')" = Succeeded ] && break; sleep 10; done
  az containerapp job show -g $G -n $JOB -o json > "$ST/$JOB.scheduled.json"; az containerapp show -g $G -n talent-api -o json > "$ST/talent-api.now.json"
  py "$H/jobcheck.py" "$ST/$JOB.scheduled.json" "$ST/talent-api.now.json" "$A/talent-api@$(dig talent-api)" Schedule || stop "$JOB schedule configuration wrong"
  date -u +%FT%TZ > "$ST/schedule.start"; ok audit-verify ;;

sync)       # Run the source sync until its snapshot is COMPLETE (at most 4 runs)
  need audit-verify; reconcile_guard
  for n in 1 2 3 4; do no_running recruitment-sync-job
    E=$(az containerapp job start -g $G -n recruitment-sync-job --query name -o tsv | tr -d '\r'); log "sync run $n: $E"; wait_exec recruitment-sync-job "$E" 1800
    jrun fresh "$ST/fresh.$n.json"
    py -c "import json,sys;sys.exit(0 if json.load(open(r'$ST/fresh.$n.json')).get('state')=='COMPLETE' else 1)" && { cp "$ST/fresh.$n.json" "$ST/fresh.json"; ok sync; exit 0; }; done
  stop "source snapshot not COMPLETE after 4 sync runs" ;;

reconcile)  # Rollback-only rehearsal with mapping gates, then exactly one reconcile, then integrity
  need sync; reconcile_guard
  jrun snap "$ST/talent.pre-reconcile.json"
  jrun rehearsal "$ST/rehearsal.json"
  jrun snap "$ST/talent.after-rehearsal.json"
  py "$H/gate.py" rehearsal-left-nothing "{k:v for k,v in a.items() if not k.startswith('outbox')}=={k:v for k,v in b.items() if not k.startswith('outbox')}" "$ST/talent.pre-reconcile.json" "$ST/talent.after-rehearsal.json"
  py - "$ST" <<'PYY' || stop "rehearsal does not meet the acceptance criteria"
import json, sys
st = sys.argv[1]; r = json.load(open(f"{st}/rehearsal.json")); res = r.get("result") or {}; tm = r.get("timing") or {}; nv = r.get("newly_verified") or []
c = {"source_complete": (r.get("upstream") or {}).get("state") == "COMPLETE" and "hold" not in r,
     "succeeded": (r.get("outcome") or [None])[0] == "SUCCEEDED", "no_conflicts": res.get("conflicts") == 0 and res.get("ambiguous") == 0,
     "existing_verified_untouched": r.get("lost_verified") == [] and r.get("changed_verified") == [],
     "new_mappings_follow_rule": all(x["now"][1] == "LEVER_DTC_TAG" and (x["tag"] or "").startswith("DTC - ") and x["clients_matching_tag_name"] == 1
                                     and x["client"] and (x["prior"] is None or (x["prior"][1] != "MANUAL" and x["prior"][2] != "REJECTED")) for x in nv),
     "processing_under_180": tm.get("reconcile_processing_s", 999) < 180}
print("ACCEPT " + json.dumps({"ok": all(c.values()), **c, "timing": tm, "newly_verified": len(nv), "promotion": res.get("promotion")}))
sys.exit(0 if all(c.values()) else 1)
PYY
  reconcile_guard; jrun run "$ST/run.json"
  py "$H/gate.py" reconcile-succeeded "a.get('http')==200 and a['body']['outcome']=='SUCCEEDED'" "$ST/run.json"
  jrun snap "$ST/talent.after-reconcile.json"
  py - "$ST" <<'PYY' || stop "post-reconcile integrity gate failed"
import json, sys
st = sys.argv[1]; b = json.load(open(f"{st}/talent.pre-reconcile.json")); a = json.load(open(f"{st}/talent.after-reconcile.json"))
p = json.load(open(f"{st}/run.json"))["body"]["counts"]["promotion"]
c = {k: a[k] == 0 for k in ("dup_candidate_request", "dup_lever_opportunity", "dup_lever_candidate", "cross_client_requests", "apps_on_unverified", "requests_per_posting_gt1")}
c |= {k: a[k] == b[k] for k in ("client_hash", "grant_hash", "clients", "magic_link_grants", "visible_apps")}
c["applications_add_up"] = a["applications"] == b["applications"] + p["applications_created"]
c["candidates_add_up"] = a["candidates"] == b["candidates"] + p["candidates_created"]
print("INTEGRITY " + json.dumps({"ok": all(c.values()), "failed": [k for k, v in c.items() if not v]})); sys.exit(0 if all(c.values()) else 1)
PYY
  reconcile_guard; ok reconcile ;;

drain)      # Wait for the schedule to deliver the reconcile's audit events (no manual change to the outbox)
  need reconcile; t=0
  while :; do jrun snap "$ST/talent.drain.json"
    py "$H/gate.py" audit-drained "a['outbox_claimed']==0 and all(s=='DELIVERED' for s,_ in a['outbox'])" "$ST/talent.drain.json" && break
    log "backlog: $(py -c "import json;a=json.load(open(r'$ST/talent.drain.json'));print(a['outbox'],'claimed',a['outbox_claimed'])")"
    [ $t -ge 5400 ] && stop "audit backlog not drained after 90 min"; sleep 300; t=$((t+300)); done
  py - "$ST" <<'PYY' || stop "data changed while draining"
import json, sys
st = sys.argv[1]; a = json.load(open(f"{st}/talent.after-reconcile.json")); b = json.load(open(f"{st}/talent.drain.json"))
sys.exit(0 if {k: v for k, v in a.items() if not k.startswith("outbox")} == {k: v for k, v in b.items() if not k.startswith("outbox")} else 1)
PYY
  az containerapp job execution list -g $G -n $JOB -o json | py -c "import json,sys,re;s=open(r'$ST/schedule.start').read().strip();f=[e['name'] for e in json.load(sys.stdin) if re.search(r'-[0-9]+$',e['name']) and e['properties']['startTime']>=s and e['properties']['status'] not in ('Succeeded','Running','Processing')];print('scheduled failures',f);sys.exit(1 if f else 0)" || stop "a scheduled drain failed"
  reconcile_guard; ok drain ;;

recruitment-finish) # after the approved secretRef restore on recruitment-api
  need platform; reconcile_guard; no_running recruitment-sync-job
  I="$A/recruitment-api@$(dig recruitment-api)"; [ "$(image_of recruitment-api)" = "$I" ] || stop "recruitment-api image not set"
  az containerapp show -g $G -n recruitment-api -o json > "$ST/recruitment-api.post.json"
  py "$H/cfgcmp.py" "$ST/recruitment-api.before.json" "$ST/recruitment-api.post.json" --allow-image || stop "recruitment-api config differs"
  job_set_image recruitment-sync-job "$I" "python scripts/run_scheduled_sync.py"; ok recruitment ;;

*) echo "phases: pre lock build suspend audit-job platform recruitment talent web audit-verify sync reconcile drain"; exit 2 ;;
esac
