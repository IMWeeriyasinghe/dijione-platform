from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.talent_request import TalentRequest


class CandidateRepository:
    """Candidate pool is global (master record, CLAUDE.md §19) — not
    tenant-scoped for an unrestricted staff caller. Client-facing visibility
    is enforced separately via Application.is_client_visible, never by
    filtering this repository. A portfolio-restricted staff caller
    (``allowed_client_ids`` not None) is the one exception: ``list_all``
    narrows to candidates with at least one application against an
    in-portfolio client, so a restricted TA's Candidate Pool list doesn't
    surface a candidate whose only applications belong to other clients."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, candidate_id: int) -> Candidate | None:
        return self.db.get(Candidate, candidate_id)

    def get_by_email(self, email: str) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.email == email)
        return self.db.execute(stmt).scalars().first()

    def get_by_lever_external_id(self, lever_external_id: str) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.lever_external_id == lever_external_id)
        return self.db.execute(stmt).scalars().first()

    def list_all(
        self, search: str | None = None, *, allowed_client_ids: list[int] | None = None
    ) -> list[Candidate]:
        stmt = select(Candidate)
        if allowed_client_ids is not None:
            stmt = (
                stmt.join(Application, Application.candidate_id == Candidate.id)
                .join(TalentRequest, TalentRequest.id == Application.talent_request_id)
                .where(TalentRequest.client_id.in_(allowed_client_ids))
                .distinct()
            )
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
