#!/usr/bin/env python3
"""Before/after HTTP measurements for the Phase 1 replica floors. Read-only.

Unauthenticated GETs through the PROD gateway (no sign-in, no business records). For each
target it records how many replicas the serving app had just before the first request
(0 = the request had to wait for a cold start), then the first-request timing and a few
warm samples.

  measure.py <phase-label>           e.g. measure.py before   |   measure.py after-t30
Writes evidence/2026-11-13/measurements-<phase-label>.tsv and prints a summary.
"""
import json, os, statistics, subprocess, sys
from datetime import datetime, timezone

BASE = os.environ.get("PHASE1_GATEWAY", "https://dijione.dijitalteam.com")
RG = os.environ.get("PHASE1_RG", "rg-dijione-prod")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("PHASE1_EVIDENCE_DIR", os.path.join(HERE, "evidence", "2026-11-13"))
# (label, path, serving app, warm samples)
TARGETS = [
    ("M1 home", "/", "shell-web", 10),
    ("M1 auth/me", "/api/auth/me", "platform-api", 10),
    ("M2 card atwork", "/api/atwork/summary", "atwork-api", 5),
    ("M2 card birthday", "/api/birthday/summary", "birthday-api", 5),
    ("M2 card onsite", "/api/onsite/summary", "onsite-api", 5),
    ("M3 open /atwork", "/atwork", "atwork-web", 10),
    ("M4 open /onsite", "/onsite", "onsite-web", 10),
    ("M9 control talent card", "/api/talent/summary", "talent-api", 0),
    ("M9 control /talent-flow", "/talent-flow", "talent-web", 0),
    ("M9 control /admin", "/admin", "admin-web", 0),
]
FMT = "%{http_code}\t%{time_connect}\t%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\t%{size_download}"


def replicas(app):
    p = subprocess.run(["az", "containerapp", "revision", "list", "-g", RG, "-n", app, "-o", "json"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        return "?"
    revs = [r for r in json.loads(p.stdout or "[]") if r["properties"].get("active")]
    return sum(r["properties"].get("replicas") or 0 for r in revs)


def get(path):
    p = subprocess.run(["curl", "-s", "-o", "/dev/null", "--max-time", "90", "--compressed", "-w", FMT, BASE + path],
                       capture_output=True, text=True)
    code, connect, tls, ttfb, total, size = (p.stdout or "000\t0\t0\t0\t0\t0").split("\t")
    return code, float(connect), float(tls), float(ttfb), float(total), int(float(size))


def main(phase):
    os.makedirs(OUT, exist_ok=True)
    rows, summary = [], []
    for label, path, app, n in TARGETS:
        rep = replicas(app)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        first = get(path)
        rows.append((stamp, phase, label, path, app, rep, "first", *first))
        warm = []
        for _ in range(n):
            s = get(path)
            rows.append((stamp, phase, label, path, app, rep, "warm", *s))
            warm.append(s[3])
        w = (f"warm p50 {statistics.median(warm)*1000:.0f} ms / max {max(warm)*1000:.0f} ms (n={n})" if warm else "")
        summary.append(f"{label:24} replicas-before={rep}  first {first[3]:6.2f}s (HTTP {first[0]}, "
                       f"connect {first[1]*1000:.0f} ms)  {w}")
    path = os.path.join(OUT, f"measurements-{phase}.tsv")
    with open(path, "w") as fh:
        fh.write("utc\tphase\tlabel\tpath\tapp\treplicas_before\tsample\thttp\tconnect_s\ttls_s\tttfb_s\ttotal_s\tbytes\n")
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")
    print(f"{phase}: {path}")
    print("\n".join(summary))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(2)
    main(sys.argv[1])
