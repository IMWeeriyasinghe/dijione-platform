"""Entry point for talent-audit-outbox-job: send pending audit events to Platform Core.

Delivers audit events only. It cannot start a reconcile or a sync. Exits 1 when
events were left for retry or refused, so the execution shows as failed.
"""

import json
import sys
from pathlib import Path

# Runnable as `python scripts/drain_audit_outbox.py` too, not only `-m`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.services.audit_outbox_service import drain  # noqa: E402


def main() -> int:
    with SessionLocal() as db:
        result = drain(db)
    # Counts only: alert on this line.
    print("audit_outbox_outcome=" + json.dumps(result))
    return 1 if result["retried"] or result["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
