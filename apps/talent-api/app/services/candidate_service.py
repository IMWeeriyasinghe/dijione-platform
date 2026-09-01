from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.candidate import Candidate
from app.repositories.application_repo import ApplicationRepository
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.interview_repo import InterviewRepository
from app.schemas.candidate import (
    CandidateApplicationSummary,
    CandidateCreate,
    CandidateOut,
    ClientSafeCandidateOut,
)


class DuplicateCandidateError(Exception):
    pass


class CandidateService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CandidateRepository(db)
        self.application_repo = ApplicationRepository(db)
        self.interview_repo = InterviewRepository(db)

    def create_candidate(self, payload: CandidateCreate) -> Candidate:
        if self.repo.get_by_email(payload.email):
            raise DuplicateCandidateError(payload.email)
        candidate = Candidate(
            full_name=payload.full_name,
            email=payload.email,
            phone=payload.phone,
            professional_title=payload.professional_title,
            summary=payload.summary,
            location=payload.location,
            skills=",".join(payload.skills),
            source=payload.source,
        )
        return self.repo.add(candidate)

    def to_out(
        self, candidate: Candidate, *, allowed_client_ids: list[int] | None = None
    ) -> CandidateOut:
        applications = self.application_repo.list_for_candidate(
            candidate.id, allowed_client_ids=allowed_client_ids
        )
        summaries = [
            CandidateApplicationSummary(
                application_id=app.id,
                client_name=app.talent_request.client.name if app.talent_request else "",
                designation=app.talent_request.designation if app.talent_request else "",
                current_stage=app.current_stage,
                status=app.status,
            )
            for app in applications
        ]
        return CandidateOut(
            id=candidate.id,
            full_name=candidate.full_name,
            email=candidate.email,
            phone=candidate.phone,
            professional_title=candidate.professional_title,
            summary=candidate.summary,
            location=candidate.location,
            availability_status=candidate.availability_status,
            skills=[s for s in candidate.skills.split(",") if s],
            cv_reference=candidate.cv_reference,
            source=candidate.source,
            applications=summaries,
            created_at=candidate.created_at,
        )

    def to_client_safe_out(self, application: Application) -> ClientSafeCandidateOut:
        candidate = application.candidate
        interviews = self.interview_repo.list_for_application(application.id)
        upcoming = next(
            (i for i in interviews if i.status == "SCHEDULED" and i.client_visible), None
        )
        return ClientSafeCandidateOut(
            application_id=application.id,
            full_name=candidate.full_name,
            professional_title=candidate.professional_title,
            skills=[s for s in candidate.skills.split(",") if s],
            relevant_experience_summary=candidate.summary,
            current_stage=application.current_stage,
            upcoming_interview_status=upcoming.status if upcoming else None,
        )
