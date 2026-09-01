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
from app.core.constants import PostingClientMappingSource, PostingClientMappingStatus
from app.db.session import get_db
from app.repositories.client_repo import ClientRepository
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.repositories.posting_repo import PostingRepository
from app.schemas.posting import ClientSafePostingOut, PostingClientMappingVerify, PostingOut

router = APIRouter(prefix="/api/talent/postings", tags=["postings"])

_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value


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
