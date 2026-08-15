from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import PostingClientMappingStatus
from app.models.posting import Posting
from app.models.posting_client_mapping import PostingClientMapping


class PostingRepository:
    """All read access to Posting visibility goes through here so the
    fail-closed Posting -> Client rule is enforced in exactly one place.

    A client-scoped caller only ever reaches a Posting via
    ``list_verified_for_client``, which inner-joins ``PostingClientMapping``
    filtered to ``status == VERIFIED AND client_id == <their own>`` — an
    unmapped or rejected Posting has no matching row and is structurally
    unreachable through this path, not merely status-flagged as hidden.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_by_lever_id(self, lever_posting_id: str) -> Posting | None:
        stmt = select(Posting).where(Posting.lever_posting_id == lever_posting_id)
        return self.db.execute(stmt).scalars().first()

    def get_by_id_for_staff(self, posting_id: int) -> Posting | None:
        stmt = select(Posting).where(Posting.id == posting_id)
        return self.db.execute(stmt).scalars().first()

    def list_for_staff(self, *, mapping_status: str | None = None) -> list[Posting]:
        stmt = select(Posting).join(Posting.client_mapping)
        if mapping_status is not None:
            stmt = stmt.where(PostingClientMapping.status == mapping_status)
        stmt = stmt.order_by(Posting.lever_updated_at.desc().nullslast())
        return list(self.db.execute(stmt).scalars().all())

    def list_unresolved(self) -> list[Posting]:
        return self.list_for_staff(mapping_status=PostingClientMappingStatus.UNMAPPED.value)

    def list_verified_for_client(self, *, client_id: int) -> list[Posting]:
        stmt = (
            select(Posting)
            .join(Posting.client_mapping)
            .where(
                PostingClientMapping.status == PostingClientMappingStatus.VERIFIED.value,
                PostingClientMapping.client_id == client_id,
            )
            .order_by(Posting.lever_updated_at.desc().nullslast())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_verified_for_client(self, posting_id: int, *, client_id: int) -> Posting | None:
        stmt = (
            select(Posting)
            .join(Posting.client_mapping)
            .where(
                Posting.id == posting_id,
                PostingClientMapping.status == PostingClientMappingStatus.VERIFIED.value,
                PostingClientMapping.client_id == client_id,
            )
        )
        return self.db.execute(stmt).scalars().first()

    def add(self, posting: Posting) -> Posting:
        self.db.add(posting)
        self.db.flush()
        return posting
