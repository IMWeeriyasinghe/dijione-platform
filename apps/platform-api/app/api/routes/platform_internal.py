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
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.db.session import get_db
from app.models.client import Client
from app.models.user import User, UserModuleRole
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/platform/internal", tags=["platform-internal"])


class ClientDirectoryRow(BaseModel):
    id: int
    public_id: str
    name: str
    status: str


@router.get("/clients", response_model=list[ClientDirectoryRow])
def list_clients(
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> list[ClientDirectoryRow]:
    """Canonical Client / Organisation directory (Architecture Completion
    Plan §6.1). The contract application services consume to resolve a
    ``client_public_id`` claim to a name/id — platform-api owns this."""
    rows = db.execute(select(Client).order_by(Client.name)).scalars().all()
    return [
        ClientDirectoryRow(id=c.id, public_id=c.public_id, name=c.name, status=c.status)
        for c in rows
    ]


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


class NotificationDeliverIn(BaseModel):
    dedupe_key: str = Field(min_length=1, max_length=200)
    type: str = Field(max_length=64)
    title: str = Field(max_length=255)
    body: str = Field(default="", max_length=2000)
    link_url: str | None = Field(default=None, max_length=500, pattern=r"^/[^/\\]")
    user_id: int | None = None
    module_key: str | None = None
    required_permissions: list[str] = Field(default_factory=list)
    exclude_user_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_target(self) -> NotificationDeliverIn:
        by_permission = bool(self.module_key and self.required_permissions)
        if (self.user_id is not None) == by_permission:
            raise ValueError("Give either user_id or module_key with required_permissions.")
        return self


@router.post("/notifications/deliver", status_code=201)
def deliver_notification(
    payload: NotificationDeliverIn,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> dict:
    """Idempotent, permission-aware delivery for services with a retrying outbox."""
    service = NotificationService(db)
    recipients = (
        service.active_users({payload.user_id})
        if payload.user_id is not None
        else service.holders_of(payload.module_key, set(payload.required_permissions))
    ) - set(payload.exclude_user_ids)
    created = service.create_once(
        user_ids=recipients,
        dedupe_key=payload.dedupe_key,
        type=payload.type,
        title=payload.title,
        body=payload.body,
        link_url=payload.link_url,
    )
    db.commit()
    return {"status": "ok", "recipients": len(recipients), "created": created}


@router.get("/users/{user_id}/modules/{module_key}/permissions")
def live_module_permissions(
    user_id: int,
    module_key: str,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> dict:
    """Current effective permissions, for services that must not trust older claims."""
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return {"active": False, "permissions": []}
    return {"active": True, "permissions": sorted(AuthorizationService(db).effective_permissions(user, module_key))}


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
