"""DijiOne Home's per-module status card (CR §15) — shell-web fetches this
independently of every other service, with its own timeout, so a talent-api
outage degrades one card instead of the whole page (CR §39). admin-api also
reads ``pending_requests`` from here to enrich its dashboard.

Unauthenticated by design: it returns aggregate counts only, no candidate/
client/request detail, so it's safe for the shell to poll without a user's
bearer token attached.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import InterviewStatus, TalentRequestLifecycleStatus
from app.db.session import get_db
from app.models.interview import Interview
from app.models.talent_request import TalentRequest

router = APIRouter(tags=["talent-summary"])


@router.get("/api/talent/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    open_requests = db.execute(
        select(func.count(TalentRequest.id)).where(
            TalentRequest.lifecycle_status.in_(
                [
                    TalentRequestLifecycleStatus.APPROVED.value,
                    TalentRequestLifecycleStatus.IN_PROGRESS.value,
                    TalentRequestLifecycleStatus.PENDING_REVIEW.value,
                ]
            )
        )
    ).scalar_one()
    pending_requests = db.execute(
        select(func.count(TalentRequest.id)).where(
            TalentRequest.lifecycle_status == TalentRequestLifecycleStatus.PENDING_REVIEW.value
        )
    ).scalar_one()
    interviews_upcoming = db.execute(
        select(func.count(Interview.id)).where(
            Interview.status == InterviewStatus.SCHEDULED.value,
            Interview.scheduled_at >= datetime.now(UTC),
        )
    ).scalar_one()
    return {
        "service": "talent-api",
        "status": "healthy",
        "open_requests": open_requests,
        "pending_requests": pending_requests,
        "interviews_upcoming": interviews_upcoming,
    }
