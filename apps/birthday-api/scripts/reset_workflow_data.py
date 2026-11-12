"""One-off DEV maintenance: reset Birthday's operational/test data to a
clean slate while preserving supplier configuration (Phase 1.6 §2/§3).

Deliberately a version-controlled script, not a permanent API endpoint —
a destructive capability like this should not live as a standing, deployed
HTTP route. The real access boundary is Azure RBAC on the resource group
(whoever can `az containerapp exec` into birthday-api), which is materially
stronger than an application-level permission check; the two in-script
guards below are a second, cheap line of defence against running this
against the wrong environment or by accident.

Usage (from apps/birthday-api, typically via `az containerapp exec`):
    python -m scripts.reset_workflow_data --environment=development --confirm=RESET-DEV-BIRTHDAY-DATA

``--environment`` must exactly match the running app's own ``app_env``
setting (read from this same process, never trusted from the caller) —
an operator who *thinks* they're targeting DEV but is actually connected
to a different container gets refused rather than silently proceeding.
``--confirm`` must exactly match the fixed literal below — a copy/paste
guard against an accidental invocation.

Clears, in this order — explicitly, one table at a time, rather than
relying on the ``ondelete="CASCADE"`` FK option: that constraint is
enforced natively in PostgreSQL (hosted DEV) but SQLite (local dev/tests)
only honours it with ``PRAGMA foreign_keys=ON`` set per-connection, which
this app does not do — so an explicit order is the one behaviour that is
correct on both backends:
    order_events, order_issues, special_requirements,
    supplier_communications                    (children of birthday_orders)
    birthday_orders
    inbound_emails           (only if EMAIL_SENDING_MODE == "mock" — these
                                 could be real external mail otherwise)
    inbound_poll_state       (reset the watermark so the next poll is clean)
    scan_runs

Preserves untouched: suppliers, supplier_users, supplier_locations,
supplier_catalogue_items, birthday_detection_configs, alembic_version.
``order_sequences`` (the per-year order-reference counter) is also left
untouched — purely cosmetic either way, not part of this reset.

All deletes run in one transaction: a failure partway rolls back
automatically, never leaving a half-cleared state.
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.audit_service import AuditService

CONFIRM_TOKEN = "RESET-DEV-BIRTHDAY-DATA"


class ResetRefusedError(Exception):
    pass


def _row_counts(db: Session) -> dict[str, int]:
    from app.models.birthday_order import BirthdayOrder
    from app.models.inbound_email import InboundEmail
    from app.models.order_event import OrderEvent
    from app.models.order_issue import OrderIssue
    from app.models.scan_run import ScanRun
    from app.models.special_requirement import SpecialRequirement
    from app.models.supplier import Supplier
    from app.models.supplier_catalogue_item import SupplierCatalogueItem
    from app.models.supplier_communication import SupplierCommunication
    from app.models.supplier_user import SupplierUser

    def _count(model) -> int:
        return db.execute(select(func.count()).select_from(model)).scalar_one()

    return {
        "birthday_orders": _count(BirthdayOrder),
        "order_events": _count(OrderEvent),
        "order_issues": _count(OrderIssue),
        "special_requirements": _count(SpecialRequirement),
        "supplier_communications": _count(SupplierCommunication),
        "inbound_emails": _count(InboundEmail),
        "scan_runs": _count(ScanRun),
        # Preserved — included in the summary purely so the operator can see
        # with their own eyes that these did not move.
        "suppliers": _count(Supplier),
        "supplier_users": _count(SupplierUser),
        "supplier_catalogue_items": _count(SupplierCatalogueItem),
    }


def reset_workflow_data(db: Session, *, confirm: str, environment: str) -> dict:
    """Deletes exactly the Phase 1.6 §3 "clear" tables; every "preserve"
    table is never touched by this function. Returns a before/after
    row-count summary. Raises ResetRefusedError (no partial effect) if
    either guard fails."""
    settings = get_settings()
    if confirm != CONFIRM_TOKEN:
        raise ResetRefusedError(f"--confirm must be exactly {CONFIRM_TOKEN!r}")
    if environment != settings.app_env:
        raise ResetRefusedError(
            f"--environment={environment!r} does not match this app's own "
            f"app_env={settings.app_env!r} — refusing to run. If you really "
            "meant to target this environment, pass its real app_env value."
        )

    from app.models.birthday_order import BirthdayOrder
    from app.models.inbound_email import InboundEmail, InboundPollState
    from app.models.order_event import OrderEvent
    from app.models.order_issue import OrderIssue
    from app.models.scan_run import ScanRun
    from app.models.special_requirement import SpecialRequirement
    from app.models.supplier_communication import SupplierCommunication

    before = _row_counts(db)

    # Children first — see the module docstring for why this isn't left to
    # ondelete="CASCADE" (SQLite doesn't enforce it without an explicit
    # PRAGMA this app doesn't set; PostgreSQL would, but the explicit order
    # is correct on both).
    db.query(OrderEvent).delete(synchronize_session=False)
    db.query(OrderIssue).delete(synchronize_session=False)
    db.query(SpecialRequirement).delete(synchronize_session=False)
    db.query(SupplierCommunication).delete(synchronize_session=False)
    db.query(BirthdayOrder).delete(synchronize_session=False)

    if settings.email_sending_mode == "mock":
        db.query(InboundEmail).delete(synchronize_session=False)
        db.query(InboundPollState).delete(synchronize_session=False)
    else:
        print(
            f"SKIPPED inbound_emails/inbound_poll_state: EMAIL_SENDING_MODE="
            f"{settings.email_sending_mode!r}, not 'mock' — these rows could be "
            "real external mail. Clear them by hand only after confirming that."
        )

    db.query(ScanRun).delete(synchronize_session=False)

    db.commit()
    after = _row_counts(db)

    try:
        AuditService().log(
            actor_id=None, action="birthday.dev.reset_workflow_data",
            entity_type="birthday_dev_reset", entity_id=0,
            previous_state=before, new_state=after,
        )
    except Exception:  # noqa: BLE001 - best-effort, never blocks the reset
        pass

    return {"before": before, "after": after}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--environment", required=True,
        help="Must exactly match this app's own app_env setting (e.g. 'development').",
    )
    parser.add_argument("--confirm", required=True, help=f"Must be exactly {CONFIRM_TOKEN!r}.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = reset_workflow_data(db, confirm=args.confirm, environment=args.environment)
    finally:
        db.close()

    print("Reset complete.")
    print("Before:", summary["before"])
    print("After: ", summary["after"])


if __name__ == "__main__":
    main()
