"""TA-facing magic-link grant management (plan B.11) — consumed by the
internal ``talent-web`` "Generate access link" screen, NOT by the external
portal. Every route is ``require_staff_scope``; a portfolio-restricted
staff member only ever sees/acts on grants for clients in their portfolio.

The raw link token and the one-time access URL are returned exactly once,
from create/regenerate only. ``GET`` never returns them — only the
non-secret ``token_prefix`` for visual disambiguation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_staff_scope
from app.db.session import get_db
from app.repositories.client_repo import ClientRepository
from app.repositories.magic_link_grant_repo import MagicLinkGrantRepository
from app.schemas.external import GrantCreatedOut, GrantCreateRequest, GrantExtendRequest, GrantOut
from app.services.magic_link_service import InvalidExpiryError, MagicLinkService

router = APIRouter(prefix="/api/talent/external/grants", tags=["talent-external-admin"])


def _client_in_scope(scope: TalentScope, client_id: int) -> bool:
    return scope.client_ids is None or client_id in scope.client_ids


def _to_out(grant, client_name: str) -> GrantOut:
    return GrantOut(
        public_id=grant.public_id,
        client_id=grant.client_id,
        client_name=client_name,
        scope_type=grant.scope_type,
        contact_name=grant.contact_name,
        contact_email=grant.contact_email,
        token_prefix=grant.token_prefix,
        status=grant.status,
        issued_by_user_id=grant.issued_by_user_id,
        issued_at=grant.issued_at,
        expires_at=grant.expires_at,
        redeemed_at=grant.redeemed_at,
        last_used_at=grant.last_used_at,
        use_count=grant.use_count,
        revoked_at=grant.revoked_at,
        revoked_by_user_id=grant.revoked_by_user_id,
    )


@router.get("", response_model=list[GrantOut])
def list_grants(
    client_id: int | None = None,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> list[GrantOut]:
    if client_id is not None and not _client_in_scope(scope, client_id):
        # Out of portfolio → empty, not 403 — no signal about the client.
        return []
    client_repo = ClientRepository(db)
    names = {c.id: c.name for c in client_repo.list_all()}
    grants = MagicLinkGrantRepository(db).list_for_scope(
        client_id=client_id, allowed_client_ids=scope.client_ids
    )
    return [_to_out(g, names.get(g.client_id, "")) for g in grants]


@router.post("", response_model=GrantCreatedOut, status_code=status.HTTP_201_CREATED)
def create_grant(
    payload: GrantCreateRequest,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> GrantCreatedOut:
    client = ClientRepository(db).get_by_id(payload.client_id)
    if client is None or not _client_in_scope(scope, client.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    service = MagicLinkService(db)
    try:
        grant, raw = service.create_grant(
            client_id=client.id,
            issued_by_user_id=scope.user.id,
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            expires_in_days=payload.expires_in_days,
            expires_at=payload.expires_at,
        )
    except InvalidExpiryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(grant)
    base = _to_out(grant, client.name)
    return GrantCreatedOut(
        **base.model_dump(), raw_token=raw, access_url=service.build_access_url(raw)
    )


def _load_in_scope(db: Session, scope: TalentScope, public_id: str):
    grant = MagicLinkGrantRepository(db).get_by_public_id(public_id)
    if grant is None or not _client_in_scope(scope, grant.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Access link not found")
    return grant


@router.post("/{public_id}/revoke", response_model=GrantOut)
def revoke_grant(
    public_id: str,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> GrantOut:
    grant = _load_in_scope(db, scope, public_id)
    MagicLinkService(db).revoke_grant(grant, revoked_by_user_id=scope.user.id)
    db.commit()
    db.refresh(grant)
    client = ClientRepository(db).get_by_id(grant.client_id)
    return _to_out(grant, client.name if client else "")


@router.post("/{public_id}/extend", response_model=GrantOut)
def extend_grant(
    public_id: str,
    payload: GrantExtendRequest,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> GrantOut:
    """Push expires_at forward on the same grant/URL — see
    MagicLinkService.extend_grant. Extend-only (never shortens), rejects a
    revoked grant (regenerate instead), accepts an already-expired-but-not-
    revoked grant (re-activates the same URL)."""
    grant = _load_in_scope(db, scope, public_id)
    try:
        MagicLinkService(db).extend_grant(
            grant,
            actor_user_id=scope.user.id,
            expires_at=payload.expires_at,
            expires_in_days=payload.expires_in_days,
        )
    except InvalidExpiryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(grant)
    client = ClientRepository(db).get_by_id(grant.client_id)
    return _to_out(grant, client.name if client else "")


@router.post("/{public_id}/regenerate", response_model=GrantCreatedOut)
def regenerate_grant(
    public_id: str,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> GrantCreatedOut:
    old = _load_in_scope(db, scope, public_id)
    service = MagicLinkService(db)
    new_grant, raw = service.regenerate_grant(old, actor_user_id=scope.user.id)
    db.commit()
    db.refresh(new_grant)
    client = ClientRepository(db).get_by_id(new_grant.client_id)
    base = _to_out(new_grant, client.name if client else "")
    return GrantCreatedOut(
        **base.model_dump(), raw_token=raw, access_url=service.build_access_url(raw)
    )
