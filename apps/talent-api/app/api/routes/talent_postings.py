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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope, require_staff_scope
from app.api.pagination import (
    TABLE_DEFAULT_PAGE_SIZE,
    TABLE_PAGE_SIZES,
    offset_for,
    require_page_size,
    total_pages,
)
from app.core.constants import (
    DtcResolutionStatus,
    PostingClientMappingSource,
    PostingClientMappingStatus,
)
from app.db.session import get_db
from app.repositories.client_repo import ClientRepository
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.repositories.posting_repo import POSTING_VIEWS, PostingRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.posting import (
    ClientSafePostingOut,
    PostingClientMappingVerify,
    PostingOut,
    PostingPageOut,
)
from app.services.audit_service import AuditService
from app.services.client_access_service import retire_request, withdraw_request_access

router = APIRouter(prefix="/api/talent/postings", tags=["postings"])

_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value
_VERIFIED = PostingClientMappingStatus.VERIFIED.value
_REJECTED = PostingClientMappingStatus.REJECTED.value
_MANUAL = PostingClientMappingSource.MANUAL.value


def _can_view(scope: TalentScope, mapping) -> bool:
    """Portfolio-restricted staff see their clients' postings and postings
    no client holds yet (needed to triage them), never another client's."""
    if scope.client_ids is None or mapping is None or mapping.client_id is None:
        return True
    return mapping.client_id in scope.client_ids


def _can_change(scope: TalentScope, mapping) -> bool:
    """A rejected mapping has no client left to scope it by, so only
    unrestricted staff may overturn one."""
    if scope.client_ids is None:
        return True
    if mapping is not None and mapping.status == _REJECTED:
        return False
    return _can_view(scope, mapping)


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
        if not _can_view(scope, mapping):
            continue
        client_name = None
        if mapping and mapping.client_id:
            client = client_repo.get_by_id(mapping.client_id)
            client_name = client.name if client else None
        out.append(_to_posting_out(ref, mapping, client_name))
    return out


@router.get("/paged", response_model=PostingPageOut)
def list_postings_staff_paged(
    view: str = Query(default="active"),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=TABLE_DEFAULT_PAGE_SIZE),
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> PostingPageOut:
    """Server-side paginated staff postings table (20/50/100, default 20).
    Display/retrieval only — no change to Lever sync, DTC resolution or
    mapping rules. ``counts`` gives every view's total under the same scope
    and search (for the filter chips and the dashboard review count)."""
    require_page_size(page_size, TABLE_PAGE_SIZES)
    if view not in POSTING_VIEWS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"view must be one of {list(POSTING_VIEWS)}"
        )
    rows, total, counts = PostingRepository(db).list_page_for_staff(
        view=view,
        search=search,
        allowed_client_ids=scope.client_ids,
        limit=page_size,
        offset=offset_for(page, page_size),
    )
    return PostingPageOut(
        items=[_to_posting_out(ref, mapping, client_name) for ref, mapping, client_name in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages(total, page_size),
        counts=counts,
    )


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
    if client is None or (scope.client_ids is not None and client.id not in scope.client_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    mapping = mapping_repo.get_or_create(ref.external_id, provider=ref.provider)
    if not _can_change(scope, mapping):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")
    previous = {"status": mapping.status, "client_id": mapping.client_id, "source": mapping.source}
    request = TalentRequestRepository(db).get_by_posting_external_id(
        ref.external_id, provider=ref.provider
    )
    retired_request_id = None
    if request is not None and request.client_id != client.id:
        retired_request_id = request.id
        retire_request(db, request)
    mapping.client_id = client.id
    mapping.status = PostingClientMappingStatus.VERIFIED.value
    mapping.source = PostingClientMappingSource.MANUAL.value
    mapping.verified_by_user_id = scope.user.id
    mapping.verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(mapping)

    AuditService().log(
        actor_id=scope.user.id,
        action="posting_mapping.manually_verified",
        entity_type="PostingClientMapping",
        entity_id=mapping.id,
        new_state={
            "previous": previous,
            "client_id": client.id,
            "posting_external_id": ref.external_id,
            "retired_request_id": retired_request_id,
        },
    )

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
    if scope.client_ids is not None and mapping.client_id not in scope.client_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")
    previous = {"status": mapping.status, "client_id": mapping.client_id, "source": mapping.source}
    request = TalentRequestRepository(db).get_by_posting_external_id(
        ref.external_id, provider=ref.provider
    )
    if request is not None:
        withdraw_request_access(request)
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
    if not _can_change(scope, mapping):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")
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
    if not _can_view(scope, mapping):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")
    client_name = None
    if mapping and mapping.client_id:
        client = client_repo.get_by_id(mapping.client_id)
        client_name = client.name if client else None
    return _to_posting_out(ref, mapping, client_name)
