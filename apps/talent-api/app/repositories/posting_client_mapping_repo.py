from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.posting_client_mapping import PostingClientMapping


class PostingClientMappingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_posting(self, posting_id: int) -> PostingClientMapping | None:
        stmt = select(PostingClientMapping).where(PostingClientMapping.posting_id == posting_id)
        return self.db.execute(stmt).scalars().first()

    def add(self, mapping: PostingClientMapping) -> PostingClientMapping:
        self.db.add(mapping)
        self.db.flush()
        return mapping
