from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.posting_client_mapping import PostingClientMapping


class PostingClientMappingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_posting(self, posting_id: int) -> PostingClientMapping | None:
        stmt = select(PostingClientMapping).where(PostingClientMapping.posting_id == posting_id)
        return self.db.execute(stmt).scalars().first()

    def list_all_with_posting(self) -> list[PostingClientMapping]:
        """Every mapping with its Posting eagerly loaded — the DTC reconciler
        iterates this once per sync run."""
        return list(
            self.db.execute(
                select(PostingClientMapping).options(
                    joinedload(PostingClientMapping.posting)
                )
            ).scalars().all()
        )

    def by_source(self, source: str) -> list[PostingClientMapping]:
        return list(
            self.db.execute(
                select(PostingClientMapping).where(PostingClientMapping.source == source)
            ).scalars().all()
        )

    def add(self, mapping: PostingClientMapping) -> PostingClientMapping:
        self.db.add(mapping)
        self.db.flush()
        return mapping
