
import json, time, httpx
from app.core.config import get_settings
s = get_settings(); t0 = time.monotonic()
try:
    r = httpx.post("http://talent-api/api/talent/internal/recruitment/reconcile", timeout=httpx.Timeout(270.0, connect=30.0),
                   headers={"X-Internal-Token": s.internal_service_secret, "X-Internal-Caller": "stage-c2-dev"})
    out = {"http": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300]}
except Exception as exc:
    out = {"error": type(exc).__name__}
out["client_elapsed_seconds"] = round(time.monotonic() - t0, 1)
print("C2R " + json.dumps(out, default=str), flush=True)
