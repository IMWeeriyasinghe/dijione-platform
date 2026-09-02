from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.posting import Posting
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
        # INNER joins on posting + candidate: a candidacy whose posting or
        # contact did not resolve locally (a confidential/filtered posting,
        # an archive-timing gap, or a stale FK) is not projectable to
        # DijiTalentFlow and would otherwise crash the DTO builder on a
        # NoneType relationship. Drop it here rather than 500 the consumer.
        stmt = (
            select(RecruitmentCandidacy)
            .join(Posting, RecruitmentCandidacy.posting_id == Posting.id)
            .join(
                RecruitmentCandidate,
                RecruitmentCandidacy.recruitment_candidate_id == RecruitmentCandidate.id,
            )
            .order_by(RecruitmentCandidacy.updated_at.desc())
        )
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
