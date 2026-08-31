"""Lever Posting read routes.

Fail-closed by construction: the client-scoped route
(``GET /api/talent/postings``) only ever reaches a Posting through
``PostingRepository.list_verified_for_client``, which inner-joins
``PostingClientMapping`` filtered to ``status == VERIFIED AND
client_id == scope.client_id`` — an unmapped or rejected Posting has no
matching row and is structurally unreachable, not merely hidden by a flag
check. Diagnostic tag/team/department text is never exposed on this path.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope, require_staff_scope
from app.core.constants import PostingClientMappingSource, PostingClientMappingStatus
from app.db.session import get_db
from app.models.posting_client_mapping import PostingClientMapping
from app.repositories.client_repo import ClientRepository
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.repositories.posting_repo import PostingRepository
from app.schemas.posting import ClientSafePostingOut, PostingClientMappingVerify, PostingOut
from app.services.lever_posting_service import LeverPostingSyncService

router = APIRouter(prefix="/api/talent/postings", tags=["postings"])


def _to_posting_out(posting, client_name: str | None) -> PostingOut:
    import json

    mapping: PostingClientMapping | None = posting.client_mapping
    return PostingOut(
        id=posting.id,
        lever_posting_id=posting.lever_posting_id,
        title=posting.title,
        state=posting.state,
        team=posting.team,
        department=posting.department,
        location=posting.location,
        confidentiality=posting.confidentiality,
        tags=json.loads(posting.tags) if posting.tags else [],
        archived=posting.archived,
        lever_created_at=posting.lever_created_at,
        lever_updated_at=posting.lever_updated_at,
        last_synced_at=posting.last_synced_at,
        mapping_status=mapping.status if mapping else PostingClientMappingStatus.UNMAPPED.value,
        mapping_client_id=mapping.client_id if mapping else None,
        mapping_client_name=client_name,
        mapping_source=mapping.source if mapping else "",
        mapping_verified_at=mapping.verified_at if mapping else None,
        dtc_source_tag=mapping.dtc_source_tag if mapping else None,
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
    postings = repo.list_unresolved() if unresolved_only else repo.list_for_staff()

    out = []
    for posting in postings:
        client_name = None
        if posting.client_mapping and posting.client_mapping.client_id:
            client = client_repo.get_by_id(posting.client_mapping.client_id)
            client_name = client.name if client else None
        out.append(_to_posting_out(posting, client_name))
    return out


@router.post("/sync")
def sync_postings(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> dict:
    """Triggers a read-only reconciliation pull from Lever (GET only — see
    LiveLeverClient's module docstring). Never assigns a client."""
    result = LeverPostingSyncService(db).sync_postings()
    db.commit()
    return result


@router.post("/{posting_id}/verify-mapping", response_model=PostingOut)
def verify_posting_mapping(
    posting_id: int,
    payload: PostingClientMappingVerify,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> PostingOut:
    """The only mechanism this phase provides for setting a Posting's
    client mapping — explicit, staff-only, source=MANUAL. No automatic
    resolution from tag/title text is implemented (CLAUDE.md §60)."""
    posting_repo = PostingRepository(db)
    mapping_repo = PostingClientMappingRepository(db)
    client_repo = ClientRepository(db)

    posting = posting_repo.get_by_id_for_staff(posting_id)
    if posting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")

    client = client_repo.get_by_id(payload.client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    mapping = mapping_repo.get_for_posting(posting.id)
    if mapping is None:
        mapping = PostingClientMapping(posting_id=posting.id)
        mapping_repo.add(mapping)

    mapping.client_id = client.id
    mapping.status = PostingClientMappingStatus.VERIFIED.value
    mapping.source = PostingClientMappingSource.MANUAL.value
    mapping.verified_by_user_id = scope.user.id
    mapping.verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(posting)

    return _to_posting_out(posting, client.name)


@router.get("/client-visible", response_model=list[ClientSafePostingOut])
def list_postings_client_scope(
    scope: TalentScope = Depends(get_talent_scope), db: Session = Depends(get_db)
) -> list[ClientSafePostingOut]:
    if scope.client_id is None:
        # Staff calling the client-facing route sees nothing here by
        # design — staff use the full diagnostic list above instead.
        return []
    repo = PostingRepository(db)
    postings = repo.list_verified_for_client(client_id=scope.client_id)
    return [
        ClientSafePostingOut(id=p.id, title=p.title, location=p.location, state=p.state)
        for p in postings
    ]


@router.get("/{posting_id}", response_model=PostingOut)
def get_posting_staff(
    posting_id: int,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> PostingOut:
    posting_repo = PostingRepository(db)
    client_repo = ClientRepository(db)
    posting = posting_repo.get_by_id_for_staff(posting_id)
    if posting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posting not found")
    client_name = None
    if posting.client_mapping and posting.client_mapping.client_id:
        client = client_repo.get_by_id(posting.client_mapping.client_id)
        client_name = client.name if client else None
    return _to_posting_out(posting, client_name)
