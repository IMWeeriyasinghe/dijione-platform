"""Service-to-service write surface (Phase 2.5 CR §27, §34).

talent-api (and, once implemented, birthday-api/spark-api) call these
endpoints to record audit events and create notifications instead of
writing to Platform Core's tables directly — AuditLog and Notification are
platform-owned. Protected by ``require_internal_service`` (a dev-only
shared secret, see ``app/api/deps.py``), never by a per-user token, since
there is no human actor behind these calls.

Callers are expected to treat failures here as non-fatal (log and continue)
— a TalentFlow action must not fail just because Platform Core is briefly
unavailable. See docs/platform/failure-isolation.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.db.session import get_db
from app.models.user import UserModuleRole
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/platform/internal", tags=["platform-internal"])


class AuditEventIn(BaseModel):
    actor_id: int | None = None
    action: str
    entity_type: str
    entity_id: int
    previous_state: dict | str | None = None
    new_state: dict | str | None = None
    metadata: dict | None = None


@router.post("/audit-events", status_code=201)
def create_audit_event(
    payload: AuditEventIn,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> dict:
    AuditService(db).log(
        actor_id=payload.actor_id,
        action=payload.action,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        previous_state=payload.previous_state,
        new_state=payload.new_state,
        metadata=payload.metadata,
    )
    db.commit()
    return {"status": "ok"}


class NotificationIn(BaseModel):
    user_id: int
    type: str
    title: str
    body: str = ""
    related_entity_type: str | None = None
    related_entity_id: int | None = None


@router.post("/notifications", status_code=201)
def create_notification(
    payload: NotificationIn,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> dict:
    NotificationService(db).notify_user(
        user_id=payload.user_id,
        type=payload.type,
        title=payload.title,
        body=payload.body,
        related_entity_type=payload.related_entity_type,
        related_entity_id=payload.related_entity_id,
    )
    db.commit()
    return {"status": "ok"}


class NotificationBroadcastIn(BaseModel):
    module_key: str
    role: str
    type: str
    title: str
    body: str = ""
    related_entity_type: str | None = None
    related_entity_id: int | None = None
    client_id: int | None = None


@router.post("/notifications/broadcast", status_code=201)
def broadcast_notification(
    payload: NotificationBroadcastIn,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> dict:
    """Notify every user holding ``role`` in ``module_key`` (optionally
    narrowed to one ``client_id``) — used e.g. to alert every Customer
    Success user when a new talent request needs review, or every
    TALENT_CLIENT user at one specific client when its request changes
    stage — which only Platform Core can resolve (it owns
    ``UserModuleRole``)."""
    NotificationService(db).notify_module_role(
        module_key=payload.module_key,
        role=payload.role,
        type=payload.type,
        title=payload.title,
        body=payload.body,
        related_entity_type=payload.related_entity_type,
        related_entity_id=payload.related_entity_id,
        client_id=payload.client_id,
    )
    db.commit()
    return {"status": "ok"}


class ModuleRoleHoldersOut(BaseModel):
    user_ids: list[int]


@router.get("/module-roles/{module_key}/{role}/user-ids", response_model=ModuleRoleHoldersOut)
def module_role_holders(
    module_key: str,
    role: str,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> ModuleRoleHoldersOut:
    stmt = select(UserModuleRole.user_id).where(
        UserModuleRole.module_key == module_key, UserModuleRole.role == role, UserModuleRole.enabled.is_(True)
    )
    return ModuleRoleHoldersOut(user_ids=[row[0] for row in db.execute(stmt).all()])
