"""cmdfix_diff.py BEFORE.json NOW.json
Exact field-by-field comparison of talent-audit-outbox-job against its copy taken
before the approved command fix. Only these differences, with exactly these values,
are allowed (approved 11 Nov; applies to this job and this comparison only):
  args            ["scripts/drain_audit_outbox.py"] -> ["-m", "scripts.drain_audit_outbox"]
  ephemeralStorage ""  -> absent   (Azure normalisation on write; no capacity change)"""
import json, sys

MISSING = object()
ALLOWED = {
    ".properties.template.containers[0].args[0]": ("scripts/drain_audit_outbox.py", "-m"),
    ".properties.template.containers[0].args[1]": (MISSING, "scripts.drain_audit_outbox"),
    ".properties.template.containers[0].resources.ephemeralStorage": ("", MISSING),
}
VOLATILE = ("systemData", "etag")
if "--image-only" in sys.argv:  # Phase A image update: the talent-api image is the only allowed change
    IMG = ".properties.template.containers[0].image"
    _a, _b = (json.load(open(f, encoding="utf-8-sig"))["properties"]["template"]["containers"][0]["image"] for f in sys.argv[1:3])
    assert _a.startswith("crdijionenonprod.azurecr.io/dijione/talent-api@sha256:") and _b.startswith("crdijionenonprod.azurecr.io/dijione/talent-api@sha256:")
    ALLOWED = {IMG: (_a, _b)}


def flat(d, p=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from flat(v, f"{p}.{k}")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from flat(v, f"{p}[{i}]")
    else:
        yield p, d


a, b = (dict(flat(json.load(open(f, encoding="utf-8-sig")))) for f in sys.argv[1:3])
diffs = {k: (a.get(k, MISSING), b.get(k, MISSING)) for k in set(a) | set(b)
         if a.get(k, MISSING) != b.get(k, MISSING) and not any(v in k for v in VOLATILE)}
unexpected = {k: v for k, v in diffs.items() if ALLOWED.get(k) != v}
missing_expected = [k for k in ALLOWED if k not in diffs]
show = lambda v: "<absent>" if v is MISSING else v
for k, (x, y) in sorted(diffs.items()):
    print(f"  {'allowed' if k not in unexpected else 'UNEXPECTED'} {k}: {show(x)!r} -> {show(y)!r}")
ok = not unexpected and not missing_expected
print("CMDFIX_DIFF " + json.dumps({"ok": ok, "unexpected": sorted(unexpected), "expected_not_seen": missing_expected}))
sys.exit(0 if ok else 1)
