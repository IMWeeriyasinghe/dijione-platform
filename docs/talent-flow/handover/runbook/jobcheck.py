"""jobcheck.py JOB.json TALENT_API.json EXPECTED_IMAGE EXPECTED_TRIGGER
Verifies talent-audit-outbox-job against the approved configuration. Exit 1 on any mismatch."""
import json, sys

job, app = (json.load(open(f, encoding="utf-8-sig")) for f in sys.argv[1:3])
image, trigger = sys.argv[3], sys.argv[4]
p, ap = job["properties"], app["properties"]
cfg, c = p["configuration"], p["template"]["containers"][0]
uai = ap["configuration"]["registries"][0]["identity"]
# Azure resource IDs are case-insensitive (e.g. resourceGroups vs resourcegroups); compare whole IDs.
same_id = lambda x, y: isinstance(x, str) and isinstance(y, str) and x.casefold() == y.casefold()
import os
ENV = os.environ.get("RB_ENV", "dev")
KV = f"https://kv-dijione-{ENV}.vault.azure.net/secrets/"
APP_ENV = {"dev": "development"}.get(ENV, ENV)
env = {e["name"]: (e.get("value"), e.get("secretRef")) for e in c.get("env") or []}
secrets = {s["name"]: (s.get("keyVaultUrl"), (s.get("identity") or "").casefold()) for s in cfg.get("secrets") or []}
assigned = list((job.get("identity") or {}).get("userAssignedIdentities", {}))
checks = {
    "image": c["image"] == image,
    "single_container": len(p["template"]["containers"]) == 1 and not p["template"].get("initContainers"),
    "environment": (p.get("environmentId") or p.get("managedEnvironmentId")).lower() == ap["environmentId"].lower(),
    "identity_user_assigned": len(assigned) == 1 and same_id(assigned[0], uai),
    "registry_identity": cfg["registries"][0]["server"] == os.environ.get("RB_REGISTRY", "crdijionenonprod") + ".azurecr.io" and same_id(cfg["registries"][0]["identity"], uai),
    "secrets_keyvault": secrets == {"database-url-talent": (KV + "database-url-talent", uai.casefold()),
                                    "internal-service-secret": (KV + "internal-service-secret", uai.casefold())},
    "env_exact": env == {"APP_ENV": (APP_ENV, None), "PLATFORM_API_URL": ("http://platform-api", None),
                         "DATABASE_URL": (None, "database-url-talent"), "INTERNAL_SERVICE_SECRET": (None, "internal-service-secret")},
    "no_recruitment_url": not any("RECRUITMENT" in k for k in env),
    # Module form: the image's working directory (/app/apps/talent-api) is first on sys.path,
    # so `app` imports. The file form put scripts/ there instead and failed at startup.
    "command": c.get("command") == ["python"] and c.get("args") == ["-m", "scripts.drain_audit_outbox"] and not c.get("workingDir"),
    "resources": float(c["resources"]["cpu"]) == 0.25 and c["resources"]["memory"] == "0.5Gi",
    "timeout_280": cfg["replicaTimeout"] == 280,
    "retry_0": cfg["replicaRetryLimit"] == 0,
    "trigger": cfg["triggerType"] == trigger,
    "parallelism_1": (cfg.get("manualTriggerConfig") or cfg.get("scheduleTriggerConfig") or {}).get("parallelism") == 1,
}
if trigger == "Schedule":
    checks["cron"] = cfg["scheduleTriggerConfig"]["cronExpression"] == "*/5 * * * *"
print("JOBCHECK " + json.dumps({"ok": all(checks.values()), **checks}))
sys.exit(0 if all(checks.values()) else 1)
