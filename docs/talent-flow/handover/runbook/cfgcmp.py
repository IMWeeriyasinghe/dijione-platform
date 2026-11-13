"""cfgcmp.py BEFORE.json AFTER.json [--allow-image]
Compares the safety-relevant configuration of a container app or job. With
--allow-image only the container image may differ. Exit 1 on any other change."""
import json, sys


def norm(d):
    p = d.get("properties", {})
    cfg, tpl = p.get("configuration", {}) or {}, p.get("template", {}) or {}
    cs = tpl.get("containers") or []
    return {
        "environment": p.get("environmentId") or p.get("managedEnvironmentId"),
        "identity": d.get("identity"),
        "registries": cfg.get("registries"),
        "secrets": sorted([(s.get("name"), s.get("keyVaultUrl"), s.get("identity")) for s in cfg.get("secrets") or []]),
        "ingress": cfg.get("ingress"),
        "trigger": [cfg.get("triggerType"), cfg.get("replicaTimeout"), cfg.get("replicaRetryLimit"),
                    (cfg.get("scheduleTriggerConfig") or {}).get("cronExpression"), (cfg.get("manualTriggerConfig") or {})],
        "running_status": p.get("runningStatus"),
        "scale": tpl.get("scale"),
        "containers": [{"name": c.get("name"), "image": c.get("image"), "command": c.get("command"), "args": c.get("args"),
                        "resources": {k: c.get("resources", {}).get(k) for k in ("cpu", "memory")},
                        "env": sorted([(e.get("name"), e.get("value"), e.get("secretRef")) for e in c.get("env") or []]),
                        "probes": c.get("probes")} for c in cs],
    }


a, b = (norm(json.load(open(f, encoding="utf-8-sig"))) for f in sys.argv[1:3])
if "--allow-image" in sys.argv:
    for c in a["containers"] + b["containers"]:
        c.pop("image")
for arg in sys.argv[3:]:   # --resources=CPU,MEM: the resources must now be exactly these; nothing else may differ
    if arg.startswith("--resources="):
        cpu, mem = arg.split("=", 1)[1].split(",")
        got = [c["resources"] for c in b["containers"]]
        if got != [{"cpu": float(cpu), "memory": mem}]:
            print(f"RESOURCES_WRONG {got}"); sys.exit(1)
        for c in a["containers"] + b["containers"]:
            c.pop("resources")
diffs = [k for k in a if a[k] != b[k]]
for k in diffs:
    print(f"CHANGED {k}:\n  before={json.dumps(a[k], default=str)[:600]}\n  after ={json.dumps(b[k], default=str)[:600]}")
print("CONFIG_IDENTICAL" if not diffs else "CONFIG_DIFFERS")
sys.exit(1 if diffs else 0)
