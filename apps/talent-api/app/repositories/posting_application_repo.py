from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.posting_application import PostingApplication


class PostingApplicationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_lever_opportunity_id(self, opportunity_id: str) -> PostingApplication | None:
        stmt = select(PostingApplication).where(
            PostingApplication.lever_opportunity_id == opportunity_id
        )
        return self.db.execute(stmt).scalars().first()

    def add(self, posting_application: PostingApplication) -> PostingApplication:
        self.db.add(posting_application)
        self.db.flush()
        return posting_application
