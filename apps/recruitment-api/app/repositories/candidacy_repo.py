from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.models.recruitment_candidate import RecruitmentCandidate


class RecruitmentCandidacyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_lever_opportunity_id(self, opportunity_id: str) -> RecruitmentCandidacy | None:
        return self.db.execute(
            select(RecruitmentCandidacy).where(
                RecruitmentCandidacy.lever_opportunity_id == opportunity_id
            )
        ).scalars().first()

    def list(self, *, posting_id: int | None = None, limit: int = 200) -> list[RecruitmentCandidacy]:
        stmt = select(RecruitmentCandidacy).order_by(RecruitmentCandidacy.updated_at.desc())
        if posting_id is not None:
            stmt = stmt.where(RecruitmentCandidacy.posting_id == posting_id)
        return list(self.db.execute(stmt.limit(limit)).scalars().all())

    def add(self, candidacy: RecruitmentCandidacy) -> RecruitmentCandidacy:
        self.db.add(candidacy)
        self.db.flush()
        return candidacy


class RecruitmentCandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_lever_contact_id(self, contact_id: str) -> RecruitmentCandidate | None:
        return self.db.execute(
            select(RecruitmentCandidate).where(
                RecruitmentCandidate.lever_contact_id == contact_id
            )
        ).scalars().first()

    def add(self, candidate: RecruitmentCandidate) -> RecruitmentCandidate:
        self.db.add(candidate)
        self.db.flush()
        return candidate
