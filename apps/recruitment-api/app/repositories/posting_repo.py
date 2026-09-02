from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.posting import Posting


class PostingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_lever_id(self, lever_posting_id: str) -> Posting | None:
        return self.db.execute(
            select(Posting).where(Posting.lever_posting_id == lever_posting_id)
        ).scalars().first()

    def count_outside(self, lever_posting_ids: Iterable[str]) -> int:
        """How many postings exist whose ``lever_posting_id`` is NOT in the
        given set — used to detect that a mock-mode sync is about to run
        against a database that already holds real, live-synced postings."""
        ids = list(lever_posting_ids)
        stmt = select(func.count()).select_from(Posting)
        if ids:
            stmt = stmt.where(Posting.lever_posting_id.notin_(ids))
        return self.db.execute(stmt).scalar_one()

    def list_all(self, *, include_archived: bool = True) -> list[Posting]:
        stmt = select(Posting)
        if not include_archived:
            stmt = stmt.where(Posting.archived.is_(False))
        stmt = stmt.order_by(Posting.lever_updated_at.desc().nullslast())
        return list(self.db.execute(stmt).scalars().all())

    def add(self, posting: Posting) -> Posting:
        self.db.add(posting)
        self.db.flush()
        return posting
