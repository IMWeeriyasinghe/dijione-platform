"""Withdrawing a client's access to a request when its posting mapping
changes. Callers commit. Nothing here ever exposes a record to a client."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.constants import TalentRequestLifecycleStatus
from app.models.talent_request import TalentRequest


def withdraw_request_access(request: TalentRequest) -> bool:
    """Unshare every candidate on the request. Returns True if any was shared."""
    changed = False
    for application in request.applications:
        if application.is_client_visible:
            application.is_client_visible = False
            changed = True
    return changed


def retire_request(db: Session, request: TalentRequest) -> None:
    """The posting now belongs to another client. Messages and documents have
    no per-record visibility, so moving this request would hand the old
    client's history to the new one. It stays with the old client for staff
    records, detached from the posting, and promotion creates a clean request."""
    withdraw_request_access(request)
    for application in request.applications:
        # Freed for the new request's applications (partial unique index).
        application.lever_opportunity_id = None
    request.provider = f"RETIRED:{request.id}"
    request.lifecycle_status = TalentRequestLifecycleStatus.CANCELLED.value
    db.flush()
