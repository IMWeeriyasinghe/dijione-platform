from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_request(self, request_id: int) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.talent_request_id == request_id)
            .order_by(Document.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def add(self, document: Document) -> Document:
        self.db.add(document)
        self.db.flush()
        return document
