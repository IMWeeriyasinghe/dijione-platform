"""Recruitment posting review + client-visibility routes.

Fail-closed by construction: the client-scoped route
(``GET /api/talent/postings/client-visible``) only ever reaches a posting
through ``PostingRepository.list_verified_for_client``, which inner-joins
``PostingClientMapping`` filtered to ``status == VERIFIED AND
client_id == scope.client_id``. Both the posting projection and the trust
record are local tables — this decision never depends on recruitment-api
being reachable. Source diagnostics are never exposed on the client path.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope, require_staff_scope
from app.core.constants import (
    DtcResolutionStatus,
    PostingClientMappingSource,
    PostingClientMappingStatus,
)
from app.db.session import get_db
from app.repositories.client_repo import ClientRepository
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.repositories.posting_repo import PostingRepository
from app.schemas.posting import ClientSafePostingOut, PostingClientMappingVerify, PostingOut
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/talent/postings", tags=["postings"])

_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value
_VERIFIED = PostingClientMappingStatus.VERIFIED.value
_REJECTED = PostingClientMappingStatus.REJECTED.value
_MANUAL = PostingClientMappingSource.MANUAL.value


def _to_posting_out(ref, mapping, client_name: str | None) -> PostingOut:
    return PostingOut(
        id=ref.id,
        external_id=ref.external_id,
        provider=ref.provider,
        title=ref.title,
        state=ref.state,
        location=ref.location,
        archived=ref.archived,
        source_synced_at=ref.source_synced_at,
        lever_created_at=ref.lever_created_at,
        mapping_status=mapping.status if mapping else _UNMAPPED,
        mapping_client_id=mapping.client_id if mapping else None,
        mapping_client_name=client_name,
        mapping_source=mapping.source if mapping else "",
        mapping_verified_at=mapping.verified_at if mapping else None,
        dtc_source_tag=mapping.dtc_source_tag if mapping else ref.dtc_raw_tag,
        dtc_client_name=ref.dtc_client_name,
        resolution_status=mapping.resolution_status if mapping else "NO_DTC_TAG",
    )


@router.get("", response_model=list[PostingOut])
def list_postings_staff(
    unresolved_only: bool = False,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> list[PostingOut]:
    repo = PostingRepository(db)
    client_repo = ClientRepository(db)
    rows = repo.list_for_staff(unresolved_only=unresolved_only)

    out: list[PostingOut] = []
    for ref, mapping in rows:
        client_name = None
        if mapping and mapping.client_id:
            client = client_repo.get_by_id(mapping.client_id)
            client_name = client.name if client else None
        out.append(_to_posting_out(ref, mapping, client_name))
    return out


@router.post("/{ref_id}/verify-mapping", response_model=PostingOut)
def verify_posting_mapping(
    ref_id: int,
    payload: PostingClientMappingVerify,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> PostingOut:
    """Staff-only, explicit, ``source=MANUAL`` client mapping — the only
    human path to set VERIFIED. A MANUAL VERIFIED mapping is never
    overwritten by later DTC reconciliation (a conflict is flagged)."""
    posting_repo = PostingRepository(db)
    mapping_repo = PostingClientMappingRepository(db)
    client_repo = ClientRepository(db)

    ref = posting_repo.get_ref_by_id(ref_id)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")

    client = client_repo.get_by_id(payload.client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    mapping = mapping_repo.get_or_create(ref.external_id, provider=ref.provider)
    mapping.client_id = client.id
    mapping.status = PostingClientMappingStatus.VERIFIED.value
    mapping.source = PostingClientMappingSource.MANUAL.value
    mapping.verified_by_user_id = scope.user.id
    mapping.verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(mapping)

    return _to_posting_out(ref, mapping, client.name)


@router.post("/{ref_id}/unmap-mapping", response_model=PostingOut)
def unmap_posting_mapping(
    ref_id: int,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> PostingOut:
    """Explicit, staff-only "Manually Unmapped" — sets REJECTED/MANUAL, the
    one mapping state the DTC reconciler treats as absolute and never
    touches (see PostingClientMappingReconciler._reconcile_one's early
    return on m.status == REJECTED). A naive reset to UNMAPPED would be
    re-VERIFIED by the very next reconcile if the posting still carries a
    valid DTC tag — REJECTED is what actually "sticks". Never calls Lever;
    the posting itself is untouched, only DijiTalentFlow's trust record."""
    posting_repo = PostingRepository(db)
    mapping_repo = PostingClientMappingRepository(db)

    ref = posting_repo.get_ref_by_id(ref_id)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")

    mapping = mapping_repo.get_or_create(ref.external_id, provider=ref.provider)
    previous = {"status": mapping.status, "client_id": mapping.client_id, "source": mapping.source}
    mapping.status = _REJECTED
    mapping.source = _MANUAL
    mapping.client_id = None
    mapping.verified_by_user_id = scope.user.id
    mapping.verified_at = datetime.now(UTC)
    mapping.resolution_status = DtcResolutionStatus.MANUALLY_UNMAPPED.value
    db.commit()
    db.refresh(mapping)

    AuditService().log(
        actor_id=scope.user.id,
        action="posting_mapping.manually_unmapped",
        entity_type="PostingClientMapping",
        entity_id=mapping.id,
        new_state={"previous": previous, "posting_external_id": ref.external_id},
    )

    return _to_posting_out(ref, mapping, None)


@router.post("/{ref_id}/reopen-mapping", response_model=PostingOut)
def reopen_posting_mapping(
    ref_id: int,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> PostingOut:
    """Undo a Manually Unmapped decision — returns the mapping to plain
    UNMAPPED so the next DTC reconcile (or a fresh manual verify) can
    resolve it again. Only meaningful from REJECTED; a no-op guard keeps it
    safe to call from any state."""
    posting_repo = PostingRepository(db)
    mapping_repo = PostingClientMappingRepository(db)

    ref = posting_repo.get_ref_by_id(ref_id)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")

    mapping = mapping_repo.get_or_create(ref.external_id, provider=ref.provider)
    previous = {"status": mapping.status, "client_id": mapping.client_id, "source": mapping.source}
    mapping.status = _UNMAPPED
    mapping.source = ""
    mapping.client_id = None
    mapping.verified_by_user_id = None
    mapping.verified_at = None
    mapping.resolution_status = DtcResolutionStatus.NO_DTC_TAG.value
    db.commit()
    db.refresh(mapping)

    AuditService().log(
        actor_id=scope.user.id,
        action="posting_mapping.reopened",
        entity_type="PostingClientMapping",
        entity_id=mapping.id,
        new_state={"previous": previous, "posting_external_id": ref.external_id},
    )

    return _to_posting_out(ref, mapping, None)


@router.get("/client-visible", response_model=list[ClientSafePostingOut])
def list_postings_client_scope(
    scope: TalentScope = Depends(get_talent_scope), db: Session = Depends(get_db)
) -> list[ClientSafePostingOut]:
    if scope.client_id is None:
        return []
    repo = PostingRepository(db)
    refs = repo.list_verified_for_client(client_id=scope.client_id)
    return [
        ClientSafePostingOut(id=r.id, title=r.title, location=r.location, state=r.state)
        for r in refs
    ]


@router.get("/{ref_id}", response_model=PostingOut)
def get_posting_staff(
    ref_id: int,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> PostingOut:
    posting_repo = PostingRepository(db)
    client_repo = ClientRepository(db)
    mapping_repo = PostingClientMappingRepository(db)

    ref = posting_repo.get_ref_by_id(ref_id)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")
    mapping = mapping_repo.get_for_posting(ref.external_id, provider=ref.provider)
    client_name = None
    if mapping and mapping.client_id:
        client = client_repo.get_by_id(mapping.client_id)
        client_name = client.name if client else None
    return _to_posting_out(ref, mapping, client_name)
