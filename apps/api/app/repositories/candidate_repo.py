from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate


class CandidateRepository:
    """Candidate pool is global (master record, CLAUDE.md §19) — not
    tenant-scoped. Client-facing visibility is enforced separately via
    Application.is_client_visible, never by filtering this repository."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, candidate_id: int) -> Candidate | None:
        return self.db.get(Candidate, candidate_id)

    def get_by_email(self, email: str) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.email == email)
        return self.db.execute(stmt).scalars().first()

    def list_all(self, search: str | None = None) -> list[Candidate]:
        stmt = select(Candidate)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (Candidate.full_name.ilike(like)) | (Candidate.professional_title.ilike(like))
            )
        stmt = stmt.order_by(Candidate.full_name)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, candidate: Candidate) -> Candidate:
        self.db.add(candidate)
        self.db.flush()
        return candidate
