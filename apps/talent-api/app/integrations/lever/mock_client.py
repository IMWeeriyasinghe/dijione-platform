from datetime import UTC, datetime, timedelta

from app.integrations.lever.client import LeverClient
from app.integrations.lever.schemas import (
    LeverInterview,
    LeverOpportunity,
    LeverPosting,
    LeverStage,
)

_NOW = datetime.now(UTC)

_POSTINGS = [
    LeverPosting(id="post-senior-ppd", text="Senior Power Platform Developer", state="published"),
    LeverPosting(id="post-senior-py", text="Senior Python Developer", state="published"),
    LeverPosting(id="post-cloud-arch", text="Cloud Solutions Architect", state="published"),
]

_STAGES = [
    LeverStage(id="stage-sourced", text="Sourced"),
    LeverStage(id="stage-screen", text="Recruiter Screen"),
    LeverStage(id="stage-client-review", text="Client Review"),
    LeverStage(id="stage-interview", text="Interview"),
    LeverStage(id="stage-offer", text="Offer"),
    LeverStage(id="stage-hired", text="Hired"),
]

_OPPORTUNITIES = [
    LeverOpportunity(
        id="opp-ron-axel-ppd",
        name="Ron Axel",
        email="ron.axel@example.com",
        headline="Senior Power Platform Developer",
        posting_id="post-senior-ppd",
        stage_id="stage-client-review",
        stage_text="Client Review",
        archived=False,
        created_at=_NOW - timedelta(days=14),
        updated_at=_NOW - timedelta(days=1),
        tags=["Power Platform", "Dataverse"],
    ),
    LeverOpportunity(
        id="opp-ron-axel-py",
        name="Ron Axel",
        email="ron.axel@example.com",
        headline="Senior Python Developer",
        posting_id="post-senior-py",
        stage_id="stage-screen",
        stage_text="Recruiter Screen",
        archived=False,
        created_at=_NOW - timedelta(days=5),
        updated_at=_NOW - timedelta(hours=6),
        tags=["Python", "Django"],
    ),
]

_INTERVIEWS = {
    "opp-ron-axel-ppd": [
        LeverInterview(
            id="int-ron-axel-ppd-1",
            opportunity_id="opp-ron-axel-ppd",
            subject="Client interview — ABC Company",
            date=_NOW + timedelta(days=2),
            feedback_status="pending",
        )
    ]
}


class MockLeverClient(LeverClient):
    """Realistic in-memory Lever data for local/demo use. Read-only, mirrors
    the shape of the real Lever API response objects it stands in for."""

    def list_postings(self) -> list[LeverPosting]:
        return list(_POSTINGS)

    def list_stages(self) -> list[LeverStage]:
        return list(_STAGES)

    def list_opportunities(self, posting_id: str | None = None) -> list[LeverOpportunity]:
        if posting_id is None:
            return list(_OPPORTUNITIES)
        return [o for o in _OPPORTUNITIES if o.posting_id == posting_id]

    def get_opportunity(self, opportunity_id: str) -> LeverOpportunity | None:
        return next((o for o in _OPPORTUNITIES if o.id == opportunity_id), None)

    def list_interviews(self, opportunity_id: str) -> list[LeverInterview]:
        return list(_INTERVIEWS.get(opportunity_id, []))
