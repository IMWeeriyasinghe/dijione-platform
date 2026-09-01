from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ApplicationStatus,
    CandidateAvailability,
    CustomerSuccessStatus,
    InterviewStatus,
    TalentRequestLifecycleStatus,
)
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.client import Client
from app.models.interview import Interview
from app.models.talent_request import TalentRequest
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.dashboard import ClientDashboardOut, TaDashboardOut
from app.services.talent_request_service import ACTIVE_APPLICATION_STATUSES, TalentRequestService


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.request_repo = TalentRequestRepository(db)
        self.request_service = TalentRequestService(db)

    def client_dashboard(self, client_id: int) -> ClientDashboardOut:
        requests = self.request_repo.list_for_scope(client_id=client_id)
        active_requests = [
            r
            for r in requests
            if r.lifecycle_status
            in {
                TalentRequestLifecycleStatus.APPROVED.value,
                TalentRequestLifecycleStatus.IN_PROGRESS.value,
                TalentRequestLifecycleStatus.PENDING_REVIEW.value,
            }
        ]
        request_ids = [r.id for r in requests]

        candidates_in_process = 0
        offers_in_progress = 0
        if request_ids:
            candidates_in_process = self.db.execute(
                select(func.count(Application.id)).where(
                    Application.talent_request_id.in_(request_ids),
                    Application.status.in_(list(ACTIVE_APPLICATION_STATUSES)),
                )
            ).scalar_one()
            offers_in_progress = self.db.execute(
                select(func.count(Application.id)).where(
                    Application.talent_request_id.in_(request_ids),
                    Application.status == ApplicationStatus.OFFER.value,
                )
            ).scalar_one()

        interviews_this_week = 0
        if request_ids:
            now = datetime.now(UTC)
            week_end = now + timedelta(days=7)
            interviews_this_week = self.db.execute(
                select(func.count(Interview.id))
                .join(Application, Interview.application_id == Application.id)
                .where(
                    Application.talent_request_id.in_(request_ids),
                    Interview.scheduled_at >= now,
                    Interview.scheduled_at <= week_end,
                    Interview.client_visible.is_(True),
                )
            ).scalar_one()

        return ClientDashboardOut(
            active_requests=len(active_requests),
            candidates_in_process=candidates_in_process,
            interviews_this_week=interviews_this_week,
            offers_in_progress=offers_in_progress,
            requests=[self.request_service.to_out(r) for r in requests],
        )

    def ta_dashboard(self, *, allowed_client_ids: list[int] | None = None) -> TaDashboardOut:
        if allowed_client_ids is not None:
            clients = len(allowed_client_ids)
        else:
            clients = self.db.execute(select(func.count(Client.id))).scalar_one()
        requests = self.request_repo.list_for_scope(
            client_id=None, allowed_client_ids=allowed_client_ids
        )
        active_requests = [
            r
            for r in requests
            if r.lifecycle_status
            in {
                TalentRequestLifecycleStatus.APPROVED.value,
                TalentRequestLifecycleStatus.IN_PROGRESS.value,
            }
        ]
        pending_review = [
            r
            for r in requests
            if r.customer_success_status == CustomerSuccessStatus.PENDING_REVIEW.value
        ]
        # Portfolio-scoped staff see counts for their assigned clients only.
        # `available_candidates` is intentionally NOT scoped — the candidate
        # pool is a global master pool with no client ownership (Architecture
        # v2 §3 / CLAUDE.md §19).
        def _scoped_app_count(stmt):
            if allowed_client_ids is not None:
                stmt = stmt.join(TalentRequest).where(
                    TalentRequest.client_id.in_(allowed_client_ids)
                )
            return self.db.execute(stmt).scalar_one()

        active_applications = _scoped_app_count(
            select(func.count(Application.id)).where(
                Application.status.in_(list(ACTIVE_APPLICATION_STATUSES))
            )
        )
        available_candidates = self.db.execute(
            select(func.count(Candidate.id)).where(
                Candidate.availability_status == CandidateAvailability.AVAILABLE.value
            )
        ).scalar_one()
        interviews_stmt = (
            select(func.count(Interview.id))
            .join(Application, Interview.application_id == Application.id)
            .where(Interview.status == InterviewStatus.SCHEDULED.value)
        )
        if allowed_client_ids is not None:
            interviews_stmt = interviews_stmt.join(
                TalentRequest, Application.talent_request_id == TalentRequest.id
            ).where(TalentRequest.client_id.in_(allowed_client_ids))
        interviews_scheduled = self.db.execute(interviews_stmt).scalar_one()
        offers_in_progress = _scoped_app_count(
            select(func.count(Application.id)).where(
                Application.status == ApplicationStatus.OFFER.value
            )
        )

        attention = sorted(
            pending_review, key=lambda r: r.created_at
        )[:10]

        return TaDashboardOut(
            clients=clients,
            active_requests=len(active_requests),
            active_applications=active_applications,
            available_candidates=available_candidates,
            interviews_scheduled=interviews_scheduled,
            offers_in_progress=offers_in_progress,
            pending_review_count=len(pending_review),
            attention_requests=[self.request_service.to_out(r) for r in attention],
        )
