"""gate.py NAME EXPR FILE [FILE2]
Evaluates a Python expression over JSON files (as a, b). Exit 1 if false.
Examples: gate.py talent-unchanged "strip(a)==strip(b)" before.json after.json"""
import json, sys

name, expr, files = sys.argv[1], sys.argv[2], sys.argv[3:]
a, b = (json.load(open(f, encoding="utf-8")) for f in files) if len(files) == 2 else (json.load(open(files[0], encoding="utf-8")), None)
DATA = ("candidates", "applications", "talent_requests", "posting_client_mappings", "clients", "magic_link_grants",
        "interviews", "messages", "documents", "recruitment_posting_refs", "map_hash", "req_hash", "app_hash",
        "client_hash", "grant_hash", "map_status", "visible")
strip = lambda d: {k: d[k] for k in DATA}
ok = bool(eval(expr, {"strip": strip, "a": a, "b": b}))
print(f"GATE {name}: {'PASS' if ok else 'FAIL'}")
if not ok and b is not None:
    for k in DATA:
        if k in a and a.get(k) != b.get(k):
            print(f"  {k}: {a.get(k)} -> {b.get(k)}")
sys.exit(0 if ok else 1)
