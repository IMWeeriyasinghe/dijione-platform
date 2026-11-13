#!/usr/bin/env python3
"""Offline scenario tests for phase1_runbook.py against fake_az.py. No Azure call is made.

Fixtures are synthetic (same shape as `az containerapp show` / `revision list` / `job list`
output, no real resource IDs). Run:  python3 deploy/runbooks/prod-replica-floor/tests/run_tests.py
"""
import json, os, shlex, shutil, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RUNBOOK = os.path.join(os.path.dirname(HERE), "phase1_runbook.py")
FAKE = os.path.join(HERE, "fake_az.py")
APPS = ["people-api", "birthday-api", "atwork-api", "atwork-web", "onsite-api", "onsite-web"]
PRINCIPAL = "operator@example.com"
TMP = tempfile.mkdtemp(prefix="phase1-runbook-tests-")
results = []


def app_json(app, i):
    port = 3000 if app.endswith("-web") else 8000
    return {"name": app, "identity": {"type": "UserAssigned", "userAssignedIdentities": {"/sub/rg/id-test": {}}},
            "properties": {
                "provisioningState": "Succeeded", "runningStatus": "Running",
                "latestRevisionName": f"{app}--0000001", "latestReadyRevisionName": f"{app}--0000001",
                "managedEnvironmentId": "/sub/rg/cae-test", "workloadProfileName": "Consumption",
                "configuration": {"activeRevisionsMode": "Single",
                                  "ingress": {"external": False, "targetPort": port,
                                              "traffic": [{"latestRevision": True, "weight": 100}]},
                                  "secrets": [{"name": "internal-service-secret", "identity": "/sub/rg/id-test",
                                               "keyVaultUrl": "https://kv-test/secrets/internal-service-secret"}],
                                  "registries": [{"server": "cr-test.azurecr.io", "identity": "/sub/rg/id-test"}]},
                "template": {"containers": [{"name": app, "image": f"cr-test.azurecr.io/dijione/{app}@sha256:{i:064d}",
                                             "env": [{"name": "APP_ENV", "value": "prod"},
                                                     {"name": "INTERNAL_SERVICE_SECRET", "secretRef": "internal-service-secret"}],
                                             "probes": [] if app.endswith("-web") else
                                             [{"type": "Readiness", "httpGet": {"path": "/health", "port": port}}],
                                             "resources": {"cpu": 0.25, "memory": "0.5Gi"}}],
                             "scale": {"minReplicas": 0, "maxReplicas": 2 if app in ("people-api", "birthday-api") else 1,
                                       "cooldownPeriod": 300, "pollingInterval": 30, "rules": None}}}}


def job(name, image_app, url=None):
    args = [f"curl -fsS -X POST {url}"] if url else ["alembic upgrade head"]
    return {"name": name, "properties": {"provisioningState": "Succeeded", "template": {"containers": [
        {"image": f"cr-test.azurecr.io/dijione/{image_app}@sha256:{'0' * 64}", "args": args}]}}}


JOBS = [job("people-sync-job", "people-api", "http://people-api/api/people/internal/scheduled-sync"),
        job("people-workforce-sync-job", "people-api", "http://people-api/api/people/internal/workforce-directory/scheduled-sync"),
        job("migrate-people-api", "people-api"),
        job("birthday-scan-job", "birthday-api", "http://birthday-api/api/birthday/internal/run-daily-scan"),
        job("birthday-comms-job", "birthday-api", "http://birthday-api/api/birthday/internal/run-comms"),
        job("migrate-birthday-api", "birthday-api"),
        job("atwork-notifications-job", "atwork-api", "http://atwork-api/api/atwork/internal/notifications/run"),
        job("migrate-atwork-api", "atwork-api"),
        job("onsite-sync-job", "onsite-api", "http://onsite-api/api/onsite/internal/scheduled-sync"),
        job("migrate-onsite-api", "onsite-api"),
        job("talent-reconcile-job", "talent-api", "http://talent-api/api/talent/internal/reconcile")]


def sandbox(name, scenario=None, execs=None, deployments=None, activity=None, mutate=None):
    root = os.path.join(TMP, name)
    for d in ("state/apps", "state/revs", "state/execs", "baseline", "run"):
        os.makedirs(os.path.join(root, d))
    for i, app in enumerate(APPS, 1):
        a = app_json(app, i)
        for target in ("baseline", "state/apps"):
            json.dump(a, open(os.path.join(root, target, f"{app}.json"), "w"))
        json.dump([{"name": f"{app}--0000001", "properties": {"active": True, "healthState": "Healthy",
                    "provisioningState": "Provisioned", "replicas": 0, "trafficWeight": 100}}],
                  open(os.path.join(root, "state/revs", f"{app}.json"), "w"))
    json.dump(JOBS, open(os.path.join(root, "state", "jobs.json"), "w"))
    for j, ex in (execs or {}).items():
        json.dump(ex, open(os.path.join(root, "state/execs", f"{j}.json"), "w"))
    json.dump(dict({"principal": PRINCIPAL}, **(scenario or {})), open(os.path.join(root, "state", "scenario.json"), "w"))
    json.dump(deployments or [], open(os.path.join(root, "state", "deployments.json"), "w"))
    json.dump(activity or [], open(os.path.join(root, "state", "activity.json"), "w"))
    if mutate:
        mutate(os.path.join(root, "state"))
    return root


def run(root, *args, approved=True, window="00:00-23:59"):
    env = dict(os.environ, PHASE1_AZ=f"{shlex.quote(sys.executable)} {shlex.quote(FAKE)}", FAKE_STATE=os.path.join(root, "state"),
               PHASE1_BASELINE_DIR=os.path.join(root, "baseline"), PHASE1_RUN_DIR=os.path.join(root, "run"),
               PHASE1_POLL_S="0", PHASE1_READY_TIMEOUT_S="2", PHASE1_JOB_WAIT_S="2", PHASE1_WINDOW_UTC=window)
    env.pop("PHASE1_APPROVED", None)
    if approved:
        env["PHASE1_APPROVED"] = "yes"
    p = subprocess.run([sys.executable, RUNBOOK, *args], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def updates(root):
    f = os.path.join(root, "state", "calls.log")
    return sum(1 for l in open(f) if l.startswith("containerapp update")) if os.path.exists(f) else 0


def app_state(root, app):
    j = json.load(open(os.path.join(root, "state/apps", f"{app}.json")))
    return j["properties"]["template"]["scale"]["minReplicas"], j["properties"]["latestReadyRevisionName"]


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"\n      {detail}" if not cond and detail else ""))


def ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def ex(name, status, mins_ago):
    return {"name": name, "properties": {"status": status,
                                         "startTime": ts(datetime.now(timezone.utc) - timedelta(minutes=mins_ago))}}


def ev(resource, when, caller=PRINCIPAL, corr="corr-own", status="Succeeded"):
    return {"operationName": {"value": "Microsoft.App/containerApps/write"}, "correlationId": corr,
            "resourceId": f"/sub/rg/providers/Microsoft.App/containerApps/{resource}",
            "eventTimestamp": ts(when), "caller": caller, "status": {"value": status}}


def own_events(root, app, corr="corr-own", caller=PRINCIPAL, offset_s=5):
    """Activity-log events as Azure would record them for the runbook's own update of `app`."""
    entry = next(e for e in json.load(open(os.path.join(root, "run", "ledger.json"))) if e["app"] == app)
    start = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
    return [ev(app, start + timedelta(seconds=offset_s + k), caller=caller, corr=corr, status=s)
            for k, s in enumerate(("Started", "Accepted", "Succeeded"))]


def set_activity(root, events):
    json.dump(events, open(os.path.join(root, "state", "activity.json"), "w"))


now = datetime.now(timezone.utc)

# --- precheck -----------------------------------------------------------------------------
r = sandbox("precheck-ok"); rc, out = run(r, "precheck")
check("precheck: live == baseline, nothing underway -> PASS", rc == 0 and "PRECHECK PASS" in out, out[-400:])


def drift_env(state):
    p = os.path.join(state, "apps", "onsite-api.json"); j = json.load(open(p))
    j["properties"]["template"]["containers"][0]["env"][0]["value"] = "changed"; json.dump(j, open(p, "w"))
r = sandbox("precheck-drift", mutate=drift_env); rc, out = run(r, "precheck")
check("precheck: env drift on onsite-api -> DRIFT, exit 1", rc == 1 and "onsite-api    DRIFT" in out, out[-400:])

r = sandbox("precheck-busy", deployments=[{"name": "atwork-prod-x", "properties": {"provisioningState": "Running"}}],
            execs={"migrate-onsite-api": [ex("m1", "Running", 1)]},
            activity=[ev("talent-api", now - timedelta(minutes=10), caller="someone@example.com", corr="c-x")])
rc, out = run(r, "precheck")
check("precheck: running deployment + migration + foreign write -> 3 BLOCKERs", rc == 1 and out.count("BLOCKER") == 3, out[-600:])

# --- apply paths --------------------------------------------------------------------------
r = sandbox("apply-ok"); rc, out = run(r, "apply", "people-api"); mn, ready = app_state(r, "people-api")
hashes = json.load(open(os.path.join(r, "run", "spec-hashes.json")))["people-api"]
check("apply ok: exit 0, 1 update, min=1, new revision ready, spec hash unchanged",
      rc == 0 and updates(r) == 1 and mn == 1 and ready.endswith("sim0001")
      and hashes["pre"]["spec_sha256"] == hashes["post"]["spec_sha256"], out[-400:])

r = sandbox("apply-slow", scenario={"update": {"atwork-web": ["slow"]}, "slow_after": 5}); rc, out = run(r, "apply", "atwork-web")
check("apply slow: waits through InProgress, then PASS", rc == 0 and updates(r) == 1 and ": PASS in" in out, out[-400:])

r = sandbox("apply-job-wait", scenario={"exec_finish_after": {"people-sync-job": 3}},
            execs={"people-sync-job": [ex("new", "Succeeded", 1), ex("old", "Running", 20)]})
rc, out = run(r, "apply", "people-api")
check("job guard: detects a running NON-latest execution, waits, then applies",
      rc == 0 and "waiting for old=Running" in out and updates(r) == 1, out[-400:])

r = sandbox("apply-job-stuck", execs={"birthday-scan-job": [ex("s", "Running", 2)]}); rc, out = run(r, "apply", "people-api")
check("job guard: indirect caller (birthday-scan-job) running -> exit 4, 0 updates", rc == 4 and updates(r) == 0, out[-400:])

r = sandbox("apply-reject", scenario={"update": {"birthday-api": ["reject"]}}); rc, out = run(r, "apply", "birthday-api")
check("rejected update: exit 6, unchanged, no rollback", rc == 6 and updates(r) == 1 and app_state(r, "birthday-api")[0] == 0, out[-400:])

r = sandbox("apply-unhealthy", scenario={"update": {"onsite-api": ["unhealthy", "ok"]}}); rc, out = run(r, "apply", "onsite-api")
mn, ready = app_state(r, "onsite-api")
check("failed revision: auto rollback, exit 5, min=0 on a fresh healthy revision",
      rc == 5 and updates(r) == 2 and mn == 0 and ready.endswith("sim0002") and "ROLLBACK PASS" in out, out[-500:])

r = sandbox("apply-partial", scenario={"update": {"atwork-api": ["partial"]}}); rc, out = run(r, "apply", "atwork-api")
check("client error after a successful change: verified as applied, exit 0",
      rc == 0 and updates(r) == 1 and app_state(r, "atwork-api")[0] == 1, out[-400:])

r = sandbox("apply-drift", scenario={"update": {"onsite-web": ["drift", "ok"]}}); rc, out = run(r, "apply", "onsite-web")
check("unexpected image change: SPEC FAIL, rollback, residual drift -> exit 7",
      rc == 7 and "SPEC CHECK FAIL" in out and "ROLLBACK FAIL" in out, out[-500:])

r = sandbox("apply-unapproved"); rc, out = run(r, "apply", "people-api", approved=False)
check("no approval flag: exit 3, 0 updates", rc == 3 and updates(r) == 0, out[-200:])

r = sandbox("apply-outside-window"); rc, out = run(r, "apply", "people-api", window="00:00-00:00")
check("outside the approved window: apply refused (exit 3, 0 updates)", rc == 3 and updates(r) == 0 and "outside the approved window" in out, out[-200:])

r = sandbox("apply-twice"); run(r, "apply", "people-api"); rc, out = run(r, "apply", "people-api")
check("second apply: stops (already min=1), still 1 update", rc == 1 and updates(r) == 1, out[-200:])

# --- rollback -----------------------------------------------------------------------------
r = sandbox("rollback-after-ok"); run(r, "apply", "birthday-api"); rc, out = run(r, "rollback", "birthday-api", window="00:00-00:00")
check("rollback after apply (also outside the window): exit 0, min=0, spec identical",
      rc == 0 and app_state(r, "birthday-api")[0] == 0 and updates(r) == 2 and "ROLLBACK PASS" in out, out[-400:])

r = sandbox("rollback-noop"); rc, out = run(r, "rollback", "onsite-web")
check("rollback at baseline: no-op, exit 0, 0 updates", rc == 0 and updates(r) == 0, out[-200:])

# --- own-write exclusion: only the runbook's own verified operations are ignored ------------
r = sandbox("own-write"); run(r, "apply", "people-api")
set_activity(r, own_events(r, "people-api"))
rc, out = run(r, "apply", "birthday-api")
led = json.load(open(os.path.join(r, "run", "ledger.json")))
check("own write (same app, same principal, inside the recorded window, one operation) ignored; id recorded",
      rc == 0 and "ignored 3 activity-log event(s)" in out and led[0]["correlation_ids"] == ["corr-own"], out[-400:])

r = sandbox("other-caller-same-app"); run(r, "apply", "people-api")
set_activity(r, own_events(r, "people-api", caller="someone@example.com", corr="c-other"))
rc, out = run(r, "apply", "birthday-api")
check("write on an updated app by ANOTHER caller inside the window -> blocks", rc == 1 and updates(r) == 1, out[-300:])

r = sandbox("same-caller-outside-window"); run(r, "apply", "people-api")
set_activity(r, own_events(r, "people-api", corr="c-later", offset_s=900))
rc, out = run(r, "apply", "birthday-api")
check("write on an updated app by the same principal OUTSIDE the recorded window -> blocks", rc == 1 and updates(r) == 1, out[-300:])

r = sandbox("two-operations-in-window"); run(r, "apply", "people-api")
set_activity(r, own_events(r, "people-api", corr="c-1") + own_events(r, "people-api", corr="c-2", offset_s=20))
rc, out = run(r, "apply", "birthday-api")
check("two operations on an updated app inside the window (ambiguous) -> blocks", rc == 1 and updates(r) == 1, out[-300:])

r = sandbox("foreign-write-other-app", activity=[ev("talent-api", now - timedelta(minutes=5), caller=PRINCIPAL, corr="c-t")])
rc, out = run(r, "apply", "birthday-api")
check("write on a service the runbook never touched (even by the same principal) -> blocks", rc == 1 and updates(r) == 0, out[-300:])

passed = sum(ok for _, ok in results)
print(f"\n{passed}/{len(results)} scenarios passed")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if passed == len(results) else 1)
