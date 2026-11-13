#!/usr/bin/env python3
"""DijiOne PROD Phase 1 - replica floors (minReplicas 0 -> 1). Gate P1-A.

  phase1_runbook.py precheck                        read-only: baseline + no deployment underway
  phase1_runbook.py audit                           read-only: where each of the six apps stands
  phase1_runbook.py status <app>                    read-only
  PHASE1_APPROVED=yes phase1_runbook.py apply <app>     one app per invocation, 17:00-18:00 UTC only
  PHASE1_APPROVED=yes phase1_runbook.py rollback <app>  any time

Order: people-api birthday-api atwork-api atwork-web onsite-api onsite-web
Exit codes: 0 ok | 1 precheck/guard failed | 2 usage | 3 not approved or outside window
            4 related job still running | 5 apply failed, rolled back | 6 update rejected, nothing changed
            7 rollback failed or residual drift - escalate (the last healthy revision keeps serving)

Environment: PHASE1_RG, PHASE1_AZ (az command, replaceable by a fake for tests), PHASE1_BASELINE_DIR,
PHASE1_RUN_DIR, PHASE1_POLL_S, PHASE1_READY_TIMEOUT_S, PHASE1_JOB_WAIT_S, PHASE1_WINDOW_UTC ("17:00-18:00"),
PHASE1_NO_AUTO_ROLLBACK=1, PHASE1_APPS (space-separated app list; default: the six Phase 1 apps).
"""
import difflib, hashlib, json, os, re, shlex, subprocess, sys, time
from datetime import datetime, timedelta, timezone

RG = os.environ.get("PHASE1_RG", "rg-dijione-prod")
AZ = shlex.split(os.environ.get("PHASE1_AZ", "az"))
POLL = float(os.environ.get("PHASE1_POLL_S", "5"))
READY_TIMEOUT = float(os.environ.get("PHASE1_READY_TIMEOUT_S", "300"))
JOB_WAIT = float(os.environ.get("PHASE1_JOB_WAIT_S", "180"))
WINDOW = os.environ.get("PHASE1_WINDOW_UTC", "17:00-18:00")
HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.environ.get("PHASE1_BASELINE_DIR", os.path.join(HERE, "evidence", "2026-11-13", "baseline"))
RUN = os.environ.get("PHASE1_RUN_DIR", os.path.join(HERE, "evidence", "2026-11-13", "run"))
LEDGER = os.path.join(RUN, "ledger.json")
APPS = os.environ.get("PHASE1_APPS", "people-api birthday-api atwork-api atwork-web onsite-api onsite-web").split()
# Jobs whose target API calls this app synchronously (verified in code, 2026-11-13).
INDIRECT = {"people-api": ["birthday-scan-job"]}
EXEC_DONE = {"Succeeded", "Failed", "Stopped", "Degraded"}          # anything else counts as running
SETTLED = {"Succeeded", "Failed", "Canceled"}
WRITE_OPS = ("microsoft.app/containerapps/write", "microsoft.app/containerapps/delete",
             "microsoft.app/jobs/write", "microsoft.app/jobs/delete",
             "microsoft.app/managedenvironments/write", "microsoft.resources/deployments/write")
OWN_SLACK_BEFORE = timedelta(seconds=60)    # activity-log timestamps vs the runbook's own clock
OWN_SLACK_AFTER = timedelta(seconds=180)


class AzError(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


_TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:?\d\d)?$")


def parse_ts(s):
    """Activity-log / ARM timestamps -> aware UTC datetime. Raises ValueError if unparseable."""
    m = _TS.match((s or "").strip())
    if not m:
        raise ValueError(f"unparseable timestamp {s!r}")
    base, frac, tz = m.groups()
    t = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    if frac:
        t = t.replace(microsecond=int(frac[:6].ljust(6, "0")))
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        t -= sign * timedelta(hours=int(tz[1:3]), minutes=int(tz[-2:]))
    return t.replace(tzinfo=timezone.utc)


def log(msg):
    line = f"{iso(now())} {msg}"
    print(line, flush=True)
    os.makedirs(RUN, exist_ok=True)
    with open(os.path.join(RUN, "execution-log.txt"), "a") as fh:
        fh.write(line + "\n")


def az(*args):
    p = subprocess.run(AZ + list(args), capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        lines = (p.stderr or p.stdout).strip().splitlines()
        raise AzError(lines[-1] if lines else f"rc={p.returncode}")
    out = p.stdout.strip()
    return json.loads(out) if out else None


def show(app):
    return az("containerapp", "show", "-g", RG, "-n", app, "-o", "json")


def revisions(app):
    return az("containerapp", "revision", "list", "-g", RG, "-n", app, "--all", "-o", "json") or []


def spec(app_json):
    """Everything that defines the app except scale.minReplicas and the revision suffix."""
    p = app_json["properties"]
    t = json.loads(json.dumps(p["template"]))
    t.pop("revisionSuffix", None)
    mn = t.get("scale", {}).pop("minReplicas", None)
    return {"template": t, "configuration": p["configuration"], "identity": app_json.get("identity"),
            "environment": p.get("managedEnvironmentId"), "workloadProfile": p.get("workloadProfileName")}, mn


def spec_hash(app_json):
    s, _ = spec(app_json)
    return hashlib.sha256(json.dumps(s, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def spec_diff(a_json, b_json):
    (a, _), (b, _) = spec(a_json), spec(b_json)
    if a == b:
        return []
    return list(difflib.unified_diff(json.dumps(a, indent=1, sort_keys=True).splitlines(),
                                     json.dumps(b, indent=1, sort_keys=True).splitlines(), lineterm="", n=1))


def load(path):
    with open(path) as fh:
        return json.load(fh)


def save(app, label, data):
    os.makedirs(RUN, exist_ok=True)
    with open(os.path.join(RUN, f"{app}.{label}.json"), "w") as fh:
        json.dump(data, fh, indent=1)
    hashes_path = os.path.join(RUN, "spec-hashes.json")
    hashes = load(hashes_path) if os.path.exists(hashes_path) else {}
    _, mn = spec(data)
    hashes.setdefault(app, {})[label] = {
        "at": iso(now()), "spec_sha256": spec_hash(data), "minReplicas": mn,
        "maxReplicas": data["properties"]["template"]["scale"].get("maxReplicas"),
        "revision": data["properties"].get("latestRevisionName"),
        "image_digest": data["properties"]["template"]["containers"][0]["image"].split("@")[-1]}
    with open(hashes_path, "w") as fh:
        json.dump(hashes, fh, indent=1, sort_keys=True)


def baseline(app):
    return load(os.path.join(BASELINE, f"{app}.json"))


# ---------- own-operation ledger -------------------------------------------------------------
_principal = None


def principal():
    global _principal
    if _principal is None:
        acct = az("account", "show", "-o", "json") or {}
        _principal = ((acct.get("user") or {}).get("name") or "").lower()
    return _principal


def ledger():
    return load(LEDGER) if os.path.exists(LEDGER) else []


def ledger_save(entries):
    os.makedirs(RUN, exist_ok=True)
    with open(LEDGER, "w") as fh:
        json.dump(entries, fh, indent=1)


def ledger_start(app, action):
    entries = ledger()
    entries.append({"app": app, "action": action, "caller": principal(), "start": iso(now()),
                    "end": None, "correlation_ids": []})
    ledger_save(entries)
    return len(entries) - 1


def ledger_end(idx):
    entries = ledger()
    entries[idx]["end"] = iso(now())
    ledger_save(entries)


def classify_writes(events):
    """Split recent write events into the runbook's own verified operations and everything else.

    An event is the runbook's own only if it belongs to an operation recorded in the ledger:
    its correlation id is already recorded there, or it is on the same app, by the same principal,
    inside that operation's recorded time window, and it is the ONLY operation (one correlation id)
    matching that window. Anything else - another caller, another time, another app, or a second
    operation inside the window - is foreign and blocks."""
    entries = ledger()
    known = {c: i for i, e in enumerate(entries) for c in e["correlation_ids"]}
    own, foreign, window_hits = [], [], {}
    for ev in events:
        corr = ev.get("correlationId") or ""
        if corr and corr in known:
            own.append(ev); continue
        target = ev.get("resourceId", "").split("/")[-1]
        caller = (ev.get("caller") or "").lower()
        try:
            ts = parse_ts(ev.get("eventTimestamp"))
        except ValueError:
            foreign.append(ev); continue                         # cannot place it in time: not ours
        hit = None
        for i, e in enumerate(entries):
            start = parse_ts(e["start"])
            end = parse_ts(e["end"]) if e["end"] else start + timedelta(seconds=READY_TIMEOUT)
            if (e["app"] == target and caller and caller == e["caller"]
                    and start - OWN_SLACK_BEFORE <= ts <= end + OWN_SLACK_AFTER):
                hit = i; break
        if hit is None:
            foreign.append(ev)
        else:
            window_hits.setdefault(hit, []).append(ev)
    changed = False
    for i, evs in window_hits.items():
        corrs = {ev.get("correlationId") or "" for ev in evs}
        if len(corrs) == 1 and "" not in corrs:
            own.extend(evs)
            entries[i]["correlation_ids"].append(corrs.pop()); changed = True
        else:
            foreign.extend(evs)                                     # ambiguous: more than one operation
    if changed:
        ledger_save(entries)
    return own, foreign


# ---------- jobs and "deployment underway" -------------------------------------------------
_jobs = None


def jobs():
    global _jobs
    if _jobs is None:
        _jobs = az("containerapp", "job", "list", "-g", RG, "-o", "json") or []
    return _jobs


def related_jobs(app):
    rel = set(INDIRECT.get(app, []))
    for j in jobs():
        text = json.dumps(j["properties"]["template"])
        if f"http://{app}/" in text or f"/dijione/{app}@" in text:
            rel.add(j["name"])
    return sorted(rel)


def running_executions(job):
    ex = az("containerapp", "job", "execution", "list", "-g", RG, "-n", job, "-o", "json") or []
    return [e for e in ex if e["properties"].get("status") not in EXEC_DONE]


def wait_jobs_idle(app):
    deadline = time.time() + JOB_WAIT
    for job in related_jobs(app):
        while True:
            run = running_executions(job)
            if not run:
                log(f"  job {job}: no execution running")
                break
            names = ", ".join(f"{e['name']}={e['properties'].get('status')}" for e in run)
            if time.time() > deadline:
                log(f"STOP: {job} still has running executions ({names}); retry after they finish")
                sys.exit(4)
            log(f"  job {job}: waiting for {names}")
            time.sleep(POLL)


def mask(caller):
    parts = (caller or "?").split("@")
    return parts[0][:3] + "***@" + parts[1] if len(parts) == 2 else parts[0][:6]


def deployment_blockers():
    """Anything suggesting another PROD deployment is underway."""
    issues = []
    for d in az("deployment", "group", "list", "-g", RG, "-o", "json") or []:
        st = d["properties"].get("provisioningState")
        if st not in SETTLED:
            issues.append(f"ARM deployment {d['name']} is {st}")
    for a in az("containerapp", "list", "-g", RG, "-o", "json") or []:
        if a["properties"].get("provisioningState") != "Succeeded":
            issues.append(f"app {a['name']} provisioningState={a['properties'].get('provisioningState')}")
    for j in jobs():
        if j["properties"].get("provisioningState") != "Succeeded":
            issues.append(f"job {j['name']} provisioningState={j['properties'].get('provisioningState')}")
        if j["name"].startswith(("migrate-", "bootstrap-")):
            for e in running_executions(j["name"]):
                issues.append(f"job {j['name']} execution {e['name']} is {e['properties'].get('status')}")
    since = iso(now() - timedelta(minutes=60))
    events = [ev for ev in (az("monitor", "activity-log", "list", "-g", RG, "--start-time", since,
                                "--max-events", "500", "-o", "json") or [])
              if (ev.get("operationName") or {}).get("value", "").lower() in WRITE_OPS]
    own, foreign = classify_writes(events)
    if own:
        log(f"  ignored {len(own)} activity-log event(s) belonging to this runbook's own recorded operations")
    seen = set()
    for ev in foreign:
        key = (ev.get("correlationId"), ev.get("resourceId"))
        if key in seen:
            continue
        seen.add(key)
        issues.append(f"recent write {(ev.get('operationName') or {}).get('value')} on "
                      f"{ev.get('resourceId', '').split('/')[-1]} at {ev.get('eventTimestamp', '')[:19]} "
                      f"by {mask(ev.get('caller'))} ({(ev.get('status') or {}).get('value')})")
    return issues


# ---------- revision state ------------------------------------------------------------------
def wait_settled(app):
    deadline = time.time() + READY_TIMEOUT
    while True:
        cur = show(app)
        st = cur["properties"].get("provisioningState")
        if st in SETTLED or time.time() > deadline:
            return cur
        time.sleep(POLL)


def wait_ready(app, old_rev, min_replicas):
    """New revision exists, is the latest ready one, healthy, provisioned, carries the traffic."""
    deadline = time.time() + READY_TIMEOUT
    info = "no new revision"
    while time.time() <= deadline:
        cur = show(app)
        latest = cur["properties"].get("latestRevisionName")
        ready = cur["properties"].get("latestReadyRevisionName")
        if latest and latest != old_rev:
            r = next((x for x in revisions(app) if x["name"] == latest), None)
            if r:
                rp = r["properties"]
                info = (f"{latest}: health={rp.get('healthState')} prov={rp.get('provisioningState')} "
                        f"replicas={rp.get('replicas')} traffic={rp.get('trafficWeight')} ready={ready}")
                if (ready == latest and rp.get("healthState") == "Healthy"
                        and rp.get("provisioningState") == "Provisioned"
                        and (rp.get("replicas") or 0) >= min_replicas and rp.get("trafficWeight") == 100):
                    return True, latest, info
        time.sleep(POLL)
    return False, None, info


def active_revisions(app):
    return [r for r in revisions(app) if r["properties"].get("active")]


def in_window():
    lo, hi = WINDOW.split("-")
    t = now().strftime("%H:%M")
    return lo <= t < hi


def require_approval(app, window=False):
    if app not in APPS:
        print(f"unknown app '{app}'"); sys.exit(2)
    if os.environ.get("PHASE1_APPROVED") != "yes":
        print("Refusing: PHASE1_APPROVED=yes is required (explicit approval, gate P1-A)"); sys.exit(3)
    if window and not in_window():
        print(f"Refusing: outside the approved window {WINDOW} UTC (now {now():%H:%M} UTC)"); sys.exit(3)


# ---------- commands ------------------------------------------------------------------------
def precheck():
    ok = True
    log(f"precheck {RG} as {mask(principal())}: live spec, revision and digest vs recorded baseline")
    for app in APPS:
        base, cur = baseline(app), show(app)
        bp, cp = base["properties"], cur["properties"]
        diff = spec_diff(base, cur)
        _, bmin = spec(base); _, cmin = spec(cur)
        state_ok = (cp.get("latestRevisionName") == bp.get("latestRevisionName")
                    and cp.get("latestReadyRevisionName") == cp.get("latestRevisionName")
                    and cp.get("provisioningState") == "Succeeded" and cmin == bmin)
        img = cp["template"]["containers"][0]["image"].split("@")[-1]
        good = state_ok and not diff
        ok &= good
        log(f"  {app:13} {'OK   ' if good else 'DRIFT'} rev={cp.get('latestRevisionName')} "
            f"min={cmin} max={cp['template']['scale'].get('maxReplicas')} {img} spec={spec_hash(cur)[:12]}")
        for line in diff[:40]:
            log(f"      {line}")
    log("precheck: other PROD deployment activity")
    blockers = deployment_blockers()
    for b in blockers:
        log(f"  BLOCKER {b}")
    if not blockers:
        log("  none: no ARM deployment running, all apps/jobs Succeeded, no migration running, "
            "no foreign Container Apps/deployment writes in the last 60 min")
    ok &= not blockers
    log("precheck: related jobs per app (checked again before each update)")
    for app in APPS:
        rel = related_jobs(app)
        running = {j: len(running_executions(j)) for j in rel}
        log(f"  {app:13} {', '.join(f'{j}({n} running)' for j, n in running.items()) or '-'}")
    log("PRECHECK PASS" if ok else "PRECHECK FAIL - stop and re-plan")
    return 0 if ok else 1


def audit():
    for app in APPS:
        cur = show(app); _, cmin = spec(cur); _, bmin = spec(baseline(app))
        act = ", ".join(f"{r['name']}({r['properties'].get('healthState')},{r['properties'].get('trafficWeight')}%,"
                        f"replicas={r['properties'].get('replicas')})" for r in active_revisions(app))
        same = "spec=baseline" if not spec_diff(baseline(app), cur) else "spec DIFFERS from baseline"
        state = "baseline" if cmin == bmin else ("APPLIED" if cmin == 1 else f"min={cmin}")
        log(f"  {app:13} {state:8} {same} prov={cur['properties'].get('provisioningState')} active: {act}")
    return 0


def status(app):
    cur = show(app); cp = cur["properties"]
    log(f"{app}: latest={cp.get('latestRevisionName')} ready={cp.get('latestReadyRevisionName')} "
        f"prov={cp.get('provisioningState')} running={cp.get('runningStatus')} "
        f"min={cp['template']['scale'].get('minReplicas')} max={cp['template']['scale'].get('maxReplicas')}")
    for r in active_revisions(app):
        rp = r["properties"]
        log(f"  active {r['name']}: health={rp.get('healthState')} prov={rp.get('provisioningState')} "
            f"running={rp.get('runningState')} replicas={rp.get('replicas')} traffic={rp.get('trafficWeight')}")
    return 0


def set_min(app, n):
    try:
        az("containerapp", "update", "-g", RG, "-n", app, "--min-replicas", str(n), "-o", "none")
        return None
    except AzError as e:
        return str(e)


def apply(app):
    require_approval(app, window=True)
    cur = wait_settled(app)
    base = baseline(app)
    if spec_diff(base, cur):
        log(f"STOP: {app} differs from the recorded baseline - run precheck"); return 1
    _, cmin = spec(cur)
    if cmin != 0:
        log(f"STOP: {app} already has minReplicas={cmin} - run audit/status"); return 1
    blockers = deployment_blockers()
    if blockers:
        for b in blockers:
            log(f"STOP: {b}")
        return 1
    wait_jobs_idle(app)
    pre = show(app); save(app, "pre", pre)
    old = pre["properties"]["latestRevisionName"]
    log(f"{app}: az containerapp update --min-replicas 1 (current revision {old}, spec {spec_hash(pre)[:12]})")
    idx = ledger_start(app, "apply")
    t0 = time.time()
    err = set_min(app, 1)
    if err:
        log(f"{app}: update command reported an error: {err}")
    cur = wait_settled(app)
    ledger_end(idx)
    if cur["properties"].get("latestRevisionName") == old:
        _, cmin = spec(cur)
        if not spec_diff(pre, cur) and cmin == 0:
            log(f"{app}: NOT APPLIED - no new revision and the spec is unchanged; nothing to roll back")
            return 6
        log(f"{app}: PARTIAL - spec changed without a new revision")
        return fail_and_rollback(app, "partial update")
    ok, latest, info = wait_ready(app, old, 1)
    post = show(app); save(app, "post", post)
    diff = spec_diff(pre, post); _, pmin = spec(post)
    if not ok:
        log(f"{app}: new revision not ready within {READY_TIMEOUT:.0f}s - {info}")
        return fail_and_rollback(app, "revision not ready")
    if diff or pmin != 1:
        log(f"{app}: SPEC CHECK FAIL (minReplicas={pmin})")
        for line in diff[:60]:
            log(f"      {line}")
        return fail_and_rollback(app, "unexpected spec change")
    deactivate_check(app, latest)
    log(f"{app}: PASS in {time.time() - t0:.0f}s - {info}; spec {spec_hash(pre)[:12]} -> {spec_hash(post)[:12]} "
        "(identical: image, env, secrets, probes, resources, ingress unchanged)")
    status(app)
    return 0


def fail_and_rollback(app, reason):
    if os.environ.get("PHASE1_NO_AUTO_ROLLBACK") == "1":
        log(f"{app}: FAIL ({reason}); auto-rollback disabled - run rollback now"); return 5
    log(f"{app}: FAIL ({reason}) - rolling back")
    rc = rollback(app)
    return 5 if rc == 0 else 7


def deactivate_check(app, latest):
    deadline = time.time() + min(90, READY_TIMEOUT)
    while True:
        others = [r["name"] for r in active_revisions(app) if r["name"] != latest]
        if not others:
            return True
        if time.time() > deadline:
            log(f"{app}: WARN still active besides {latest}: {', '.join(others)} - inspect; deactivate with "
                f"'az containerapp revision deactivate -g {RG} -n {app} --revision <name>' if unhealthy")
            return False
        time.sleep(POLL)


def rollback(app):
    require_approval(app)
    ref_path = os.path.join(RUN, f"{app}.pre.json")
    ref = load(ref_path) if os.path.exists(ref_path) else baseline(app)
    _, rmin = spec(ref)
    cur = wait_settled(app)
    _, cmin = spec(cur)
    cp = cur["properties"]
    healthy_latest = (cp.get("latestReadyRevisionName") == cp.get("latestRevisionName"))
    if cmin == rmin and not spec_diff(ref, cur) and healthy_latest:
        log(f"{app}: already at minReplicas={rmin} with a healthy latest revision - nothing to roll back")
        deactivate_check(app, cp.get("latestRevisionName"))
        return 0
    old = cp.get("latestRevisionName")
    log(f"{app}: ROLLBACK az containerapp update --min-replicas {rmin} (latest {old}, "
        f"ready {cp.get('latestReadyRevisionName')})")
    idx = ledger_start(app, "rollback")
    err = set_min(app, rmin)
    if err:
        log(f"{app}: rollback command reported an error: {err}")
    wait_settled(app)
    ledger_end(idx)
    ok, latest, info = wait_ready(app, old, 0)
    after = show(app); save(app, "rollback", after)
    diff = spec_diff(ref, after); _, amin = spec(after)
    if ok and not diff and amin == rmin:
        deactivate_check(app, latest)
        log(f"{app}: ROLLBACK PASS - {info}; spec identical to the pre-change state ({spec_hash(after)[:12]})")
        return 0
    log(f"{app}: ROLLBACK FAIL - {info}; minReplicas={amin}; the last healthy revision keeps serving. "
        "Escalate; do not retry blindly.")
    for line in diff[:60]:
        log(f"      {line}")
    return 7


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    app = argv[2] if len(argv) > 2 else ""
    try:
        if cmd == "precheck":
            return precheck()
        if cmd == "audit":
            return audit()
        if cmd == "status" and app in APPS:
            return status(app)
        if cmd == "apply" and app:
            return apply(app)
        if cmd == "rollback" and app:
            return rollback(app)
    except AzError as e:
        log(f"az error: {e} - stop; run audit"); return 7
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
