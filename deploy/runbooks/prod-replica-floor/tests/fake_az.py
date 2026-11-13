#!/usr/bin/env python3
"""Fake `az` for offline runbook tests. State lives in $FAKE_STATE; nothing touches Azure."""
import json, os, sys

S = os.environ["FAKE_STATE"]
a = sys.argv[1:]


def rd(p, default=None):
    f = os.path.join(S, p)
    return json.load(open(f)) if os.path.exists(f) else default


def wr(p, d):
    f = os.path.join(S, p)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    json.dump(d, open(f, "w"))


def arg(name):
    return a[a.index(name) + 1] if name in a else None


def out(d):
    print(json.dumps(d))
    sys.exit(0)


def tick(key):
    c = rd("counters.json", {})
    c[key] = c.get(key, 0) + 1
    wr("counters.json", c)
    return c[key]


with open(os.path.join(S, "calls.log"), "a") as fh:
    fh.write(" ".join(a) + "\n")
scen = rd("scenario.json", {})

if a[:2] == ["account", "show"]:
    out({"user": {"name": scen.get("principal", "operator@example.com"), "type": "user"}})
if a[:2] == ["containerapp", "show"]:
    app = arg("-n")
    pend = rd(f"pending/{app}.json")
    if pend and tick("show:" + app) >= pend["after"]:          # slow revision becomes ready
        appj, revs = rd(f"apps/{app}.json"), rd(f"revs/{app}.json")
        for r in revs:
            r["properties"]["active"] = r["name"] == pend["rev"]
            r["properties"]["trafficWeight"] = 100 if r["name"] == pend["rev"] else 0
            if r["name"] == pend["rev"]:
                r["properties"].update(healthState="Healthy", provisioningState="Provisioned", replicas=1)
        appj["properties"].update(latestReadyRevisionName=pend["rev"], provisioningState="Succeeded")
        wr(f"apps/{app}.json", appj); wr(f"revs/{app}.json", revs)
        os.remove(os.path.join(S, f"pending/{app}.json"))
    out(rd(f"apps/{app}.json"))
if a[:2] == ["containerapp", "list"]:
    out([rd(f"apps/{f}") for f in sorted(os.listdir(os.path.join(S, "apps")))])
if a[:3] == ["containerapp", "revision", "list"]:
    out(rd(f"revs/{arg('-n')}.json", []))
if a[:3] == ["containerapp", "job", "list"]:
    out(rd("jobs.json", []))
if a[:4] == ["containerapp", "job", "execution", "list"]:
    job = arg("-n")
    ex = rd(f"execs/{job}.json", [])
    fin = scen.get("exec_finish_after", {}).get(job)
    if fin is not None and tick("exec:" + job) > fin:
        for e in ex:
            if e["properties"]["status"] == "Running":
                e["properties"]["status"] = "Succeeded"
        wr(f"execs/{job}.json", ex)
    out(ex)
if a[:3] == ["deployment", "group", "list"]:
    out(rd("deployments.json", []))
if a[:3] == ["monitor", "activity-log", "list"]:
    out(rd("activity.json", []))
if a[:2] == ["containerapp", "update"]:
    app, n = arg("-n"), int(arg("--min-replicas"))
    k = tick("update:" + app)
    modes = scen.get("update", {}).get(app) or ["ok"]
    mode = modes[min(k, len(modes)) - 1]
    if mode == "reject":
        print("ERROR: (Conflict) simulated rejection", file=sys.stderr); sys.exit(1)
    appj, revs = rd(f"apps/{app}.json"), rd(f"revs/{app}.json", [])
    new = f"{app}--sim{k:04d}"
    appj["properties"]["template"]["scale"]["minReplicas"] = n
    appj["properties"]["latestRevisionName"] = new
    if mode == "drift":
        c = appj["properties"]["template"]["containers"][0]
        c["image"] = c["image"][:-4] + "dead"
    rev = {"name": new, "properties": {"active": True, "healthState": "Healthy", "provisioningState": "Provisioned",
                                       "replicas": 1 if n else 0, "trafficWeight": 100}}
    if mode in ("ok", "partial", "drift"):
        appj["properties"].update(latestReadyRevisionName=new, provisioningState="Succeeded")
        for r in revs:
            r["properties"]["active"] = False; r["properties"]["trafficWeight"] = 0
    elif mode == "slow":
        rev["properties"].update(healthState="None", provisioningState="Provisioning", replicas=0, trafficWeight=0)
        appj["properties"]["provisioningState"] = "InProgress"
        wr(f"pending/{app}.json", {"rev": new, "after": scen.get("slow_after", 4)})
    elif mode == "unhealthy":
        rev["properties"].update(healthState="Unhealthy", provisioningState="Failed", replicas=0, trafficWeight=0)
        appj["properties"]["provisioningState"] = "Failed"
    revs.append(rev)
    wr(f"apps/{app}.json", appj); wr(f"revs/{app}.json", revs)
    if mode in ("partial", "unhealthy"):
        print("ERROR: simulated client timeout / failed operation", file=sys.stderr); sys.exit(1)
    sys.exit(0)
print("fake az: unsupported " + " ".join(a), file=sys.stderr)
sys.exit(2)
