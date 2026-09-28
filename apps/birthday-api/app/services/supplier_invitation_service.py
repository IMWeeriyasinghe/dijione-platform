"""Supplier Portal invitation — sends DIJI's own branded email over the
existing Graph mail transport (packages/mail-client-py, same shared
mailbox as the order-release notification). Never creates or touches an
Entra B2B guest object: this tenant already provisions the guest
just-in-time on first sign-in (confirmed live), so the only thing this
app needs to do is get the supplier a correct, working portal link —
Entra handles the rest exactly as it already does today.

Idempotent by design at the data layer: sending again only ever updates
invited_at/invite_count/last_invited_by on the same row — it can never
create a second SupplierUser or a second Entra guest, because it never
creates either.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import CommunicationChannel
from app.integrations.factory import get_email_client
from app.models.supplier_user import SupplierUser
from app.services.audit_service import AuditService
from app.services.supplier_invitation_email_template import render_supplier_invitation_email

_BUSINESS_ACCEPTED_OUTCOMES = {"SIMULATED", "SUBMITTED"}


class SupplierUserNotEligibleError(Exception):
    """Raised when an invite is requested for a user that cannot receive
    one right now (deactivated, or no email on file)."""


@dataclass(frozen=True)
class InvitationSendResult:
    sent: bool
    detail: str


def _validate_eligible(user: SupplierUser) -> None:
    if user.status != "ACTIVE":
        raise SupplierUserNotEligibleError(
            "This supplier user is deactivated — reactivate the account before sending an invitation."
        )
    if not user.email:
        raise SupplierUserNotEligibleError("This supplier user has no email address on file.")


def send_supplier_invitation(
    db: Session,
    user: SupplierUser,
    *,
    actor_id: int | None,
    automatic: bool,
) -> InvitationSendResult:
    """Sends the branded invitation email and records the outcome on the
    row + in the shared AuditLog. Raises SupplierUserNotEligibleError
    without sending anything (and without touching the row) if the user
    isn't currently eligible — callers decide how to surface that.

    Never raises for a mail-transport failure: that is reported back via
    InvitationSendResult.sent=False so a caller (manual resend, or the
    auto-invite-on-create path) can report a clear, honest message instead
    of a 500 or a silently-wrong success claim.
    """
    _validate_eligible(user)

    supplier_name = user.supplier.name if user.supplier else ""
    content = render_supplier_invitation_email(user, supplier_name)

    audit_metadata = {
        "recipient": user.email,
        "automatic": automatic,
        "supplier_id": user.supplier_id,
    }

    try:
        result = get_email_client(db).send(
            to=user.email, subject=content.subject, body=content.html_body, content_type="HTML"
        )
    except Exception as exc:  # noqa: BLE001 - a transport failure must never propagate raw
        AuditService().log(
            actor_id=actor_id, action="birthday.supplier_user.invite_failed",
            entity_type="supplier_user", entity_id=user.id,
            metadata={**audit_metadata, "error": str(exc)},
        )
        return InvitationSendResult(sent=False, detail=f"Invitation could not be sent: {exc}")

    accepted = result.outcome.value in _BUSINESS_ACCEPTED_OUTCOMES
    if not accepted:
        detail = result.error or f"Graph transport reported {result.outcome.value}"
        AuditService().log(
            actor_id=actor_id, action="birthday.supplier_user.invite_failed",
            entity_type="supplier_user", entity_id=user.id,
            metadata={**audit_metadata, "transport_outcome": result.outcome.value, "error": detail},
        )
        return InvitationSendResult(sent=False, detail=f"Invitation could not be sent: {detail}")

    user.invited_at = datetime.now(UTC)
    user.invite_count = (user.invite_count or 0) + 1
    user.last_invited_by = actor_id
    db.commit()

    AuditService().log(
        actor_id=actor_id, action="birthday.supplier_user.invite_sent",
        entity_type="supplier_user", entity_id=user.id,
        metadata={**audit_metadata, "transport_outcome": result.outcome.value, "channel": CommunicationChannel.EMAIL.value},
    )
    return InvitationSendResult(sent=True, detail=f"Invitation sent to {user.email}.")
