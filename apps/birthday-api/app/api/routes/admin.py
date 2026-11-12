"""Admin-only, user-auth-gated surface for operational actions that
otherwise only exist behind the service-to-service internal secret (plan
§7). Calls the exact same ``run_daily_scan`` service the production
external scheduler and ``internal.py`` call — no detection logic is
duplicated here, this is purely an auth-appropriate wrapper for UAT/ops."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission, require_non_production
from app.api.routes.config import get_or_create_config
from app.api.routes.internal import _scan_run_to_dict
from app.db.session import get_db
from app.integrations.factory import get_employee_source
from app.models.scan_run import ScanRun
from app.schemas.test_email_recipient import (
    TestEmailRecipientCreate,
    TestEmailRecipientListResponse,
    TestEmailRecipientRead,
    TestEmailRecipientUpdate,
)
from app.services import attention_service
from app.services import test_email_recipient_service as recipients
from app.services.audit_service import AuditService
from app.services.detection_service import run_daily_scan

router = APIRouter(prefix="/api/birthday/admin", tags=["birthday-admin"])


@router.post("/run-detection")
def run_detection(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> dict:
    config = get_or_create_config(db)
    client = get_employee_source()
    return run_daily_scan(db, client, config, trigger="MANUAL")


@router.post("/run-attention")
def run_attention(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> dict:
    """Auth-gated attention/detection-health sweep for UAT/ops — same
    service ``birthday-attention-job`` calls."""
    return attention_service.run_attention_sweep(db)


@router.get("/scan-runs")
def list_scan_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> list[dict]:
    """Same scan-run history as internal.py's service-to-service route,
    exposed to authenticated admin users so the internal UI can show it
    without needing the shared internal-service secret."""
    limit = max(1, min(limit, 100))
    runs = db.query(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit).all()
    return [_scan_run_to_dict(r) for r in runs]


# -- Email Safety (non-production outbound-recipient allowlist) ----------
# DijiBirthday-owned (docs/platform/email-architecture.md) — deliberately
# NOT in DijiOne platform-level admin. require_non_production() is checked
# FIRST on every route below (before any permission/DB work), independent
# of the birthday-web nav item, so PROD 404s the entire surface regardless
# of what the frontend shows.
_TEST_EMAIL_RECIPIENT_ENTITY = "birthday_test_email_recipient"


def _audit_recipient(
    scope: BirthdayScope, action: str, entity_id: int, *, previous_state: dict | None = None,
    new_state: dict | None = None,
) -> None:
    try:
        AuditService().log(
            actor_id=scope.user.id, action=action, entity_type=_TEST_EMAIL_RECIPIENT_ENTITY,
            entity_id=entity_id, previous_state=previous_state, new_state=new_state,
        )
    except Exception:  # noqa: BLE001 - best-effort, matches every other audit call in this app
        pass


@router.get("/test-email-recipients", response_model=TestEmailRecipientListResponse)
def list_test_email_recipients(
    _env: None = Depends(require_non_production),
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> TestEmailRecipientListResponse:
    return TestEmailRecipientListResponse(items=recipients.list_recipients(db))


@router.post(
    "/test-email-recipients", status_code=status.HTTP_201_CREATED, response_model=TestEmailRecipientRead
)
def create_test_email_recipient(
    payload: TestEmailRecipientCreate,
    _env: None = Depends(require_non_production),
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> TestEmailRecipientRead:
    try:
        recipient = recipients.create_recipient(
            db, email_address=payload.email_address, display_label=payload.display_label,
            recipient_type=payload.recipient_type, is_active=payload.is_active,
            actor_id=scope.user.id,
        )
    except recipients.DuplicateRecipientError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except recipients.InvalidEmailError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    db.refresh(recipient)
    _audit_recipient(
        scope, "TEST_EMAIL_RECIPIENT_CREATED", recipient.id,
        new_state={"email_address": recipient.email_address, "recipient_type": recipient.recipient_type},
    )
    return recipient


@router.patch("/test-email-recipients/{recipient_id}", response_model=TestEmailRecipientRead)
def update_test_email_recipient(
    recipient_id: int,
    payload: TestEmailRecipientUpdate,
    _env: None = Depends(require_non_production),
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> TestEmailRecipientRead:
    recipient = recipients.get_recipient_or_none(db, recipient_id)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test email recipient not found")

    updates = payload.model_dump(exclude_unset=True)
    previous_state = {
        "display_label": recipient.display_label, "recipient_type": recipient.recipient_type,
        "is_active": recipient.is_active,
    }
    was_active = recipient.is_active
    try:
        recipient = recipients.update_recipient(db, recipient, updates, actor_id=scope.user.id)
    except recipients.InvalidEmailError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    db.refresh(recipient)

    new_state = {
        "display_label": recipient.display_label, "recipient_type": recipient.recipient_type,
        "is_active": recipient.is_active,
    }
    # A dedicated activate/deactivate event when that's specifically what
    # changed, in addition to the general "updated" event — mirrors the
    # supplier-user Entra-link pattern (routes/suppliers.py) of logging the
    # security-relevant transition distinctly from a routine field edit.
    if "is_active" in updates and updates["is_active"] != was_active:
        action = "TEST_EMAIL_RECIPIENT_ACTIVATED" if recipient.is_active else "TEST_EMAIL_RECIPIENT_DEACTIVATED"
        _audit_recipient(scope, action, recipient.id, previous_state=previous_state, new_state=new_state)
    else:
        _audit_recipient(
            scope, "TEST_EMAIL_RECIPIENT_UPDATED", recipient.id,
            previous_state=previous_state, new_state=new_state,
        )
    return recipient


@router.delete("/test-email-recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_email_recipient(
    recipient_id: int,
    _env: None = Depends(require_non_production),
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> None:
    """Prefer deactivation (PATCH is_active=false) in the UI — this exists
    for cleaning up a genuine mistake (a typo'd address that was never a
    real approved recipient), not as the normal offboarding path, mirroring
    this app's general preference for status flips over row deletion."""
    recipient = recipients.get_recipient_or_none(db, recipient_id)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test email recipient not found")
    email_address = recipient.email_address
    db.delete(recipient)
    db.commit()
    _audit_recipient(scope, "TEST_EMAIL_RECIPIENT_REMOVED", recipient_id, previous_state={"email_address": email_address})
