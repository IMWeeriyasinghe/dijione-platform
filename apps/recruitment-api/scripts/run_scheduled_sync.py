"""Entry point for recruitment-sync-job: start a sync and wait for its result.

Polling keeps HTTP traffic on recruitment-api, so the replica cannot scale to
zero under the background run, and the job's own status reports the outcome.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("RECRUITMENT_API_URL", "http://recruitment-api") + "/api/recruitment"
POLL_SECONDS = 20.0
DEADLINE_SECONDS = 1500.0  # inside the job's 1800 s replica timeout
TRANSIENT_POLL_LIMIT = 10
TERMINAL = {"SUCCEEDED", "PARTIAL", "FAILED"}


def call(method: str, path: str) -> dict:
    request = urllib.request.Request(
        BASE + path, method=method,
        headers={
            "X-Internal-Token": os.environ["INTERNAL_SERVICE_SECRET"],
            "X-Internal-Caller": "recruitment-sync-job",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read() or b"{}")


def main() -> int:
    try:
        # A retried execution attaches to the active run instead of starting another.
        run_id = call("POST", "/internal/scheduled-sync")["run_id"]
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"sync_outcome=NOT_STARTED error={type(exc).__name__}", file=sys.stderr)
        return 1
    started = time.monotonic()
    transient = 0
    while time.monotonic() - started < DEADLINE_SECONDS:
        time.sleep(POLL_SECONDS)
        try:
            run = call("GET", f"/sync/{run_id}")["run"] or {}
        except (urllib.error.URLError, TimeoutError):
            transient += 1
            if transient >= TRANSIENT_POLL_LIMIT:
                print(f"sync_outcome=UNKNOWN run_id={run_id} error=status_unavailable", file=sys.stderr)
                return 1
            continue
        transient = 0
        if run.get("status") in TERMINAL:
            # PARTIAL exits 0 because later runs continue the read. Alert on this line:
            # only source_snapshot COMPLETE means the data refresh is complete.
            print(f"sync_outcome={run['status']} " + json.dumps({k: run.get(k) for k in ("run_id", "error_summary", "detail")}))
            return 1 if run["status"] == "FAILED" else 0
    print(f"sync_outcome=UNKNOWN run_id={run_id} error=deadline", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
