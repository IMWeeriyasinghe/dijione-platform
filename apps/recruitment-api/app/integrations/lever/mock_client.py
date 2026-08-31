from datetime import UTC, datetime, timedelta

from app.integrations.lever.client import LeverClient
from app.integrations.lever.schemas import (
    LeverApplication,
    LeverArchiveReason,
    LeverInterview,
    LeverOfferSummary,
    LeverOpportunity,
    LeverPosting,
    LeverStage,
    LeverStageChange,
    LeverUser,
)

_NOW = datetime.now(UTC)

_POSTINGS = [
    LeverPosting(
        id="post-senior-ppd", text="Senior Power Platform Developer", state="published",
        team="Other", location="Sri Lanka", owner_user_id="user-recruiter-1",
        tags=["Power Platform Developer"],
    ),
    LeverPosting(
        id="post-senior-py", text="Senior Python Developer", state="published",
        team="Other", location="Sri Lanka", owner_user_id="user-recruiter-1",
        tags=["Python Developer"],
    ),
    LeverPosting(
        id="post-cloud-arch", text="Cloud Solutions Architect", state="published",
        team="Other", location="Sri Lanka", owner_user_id="user-recruiter-2",
        tags=["Cloud Solutions Architect"],
    ),
]

# Real 14-stage pipeline confirmed by live Lever tenant discovery — mirrors
# the actual Dijital Team stage catalogue, not a generic assumption.
_STAGES = [
    LeverStage(id="lead-new", text="New lead"),
    LeverStage(id="lead-reached-out", text="Reached out"),
    LeverStage(id="lead-responded", text="Responded"),
    LeverStage(id="applicant-new", text="New applicant"),
    LeverStage(id="stage-recruiter-phone-screen", text="Recruiter Phone Screen"),
    LeverStage(id="stage-sparkhire", text="SparkHire Assessment Stage"),
    LeverStage(id="stage-testgorilla", text="TestGorilla Assessment"),
    LeverStage(id="stage-sme-interview", text="SME Interview"),
    LeverStage(id="stage-predictive-talent-assessment", text="Predictive Talent Assessment"),
    LeverStage(id="stage-presented-to-customer", text="Presented to Customer"),
    LeverStage(id="stage-client-interview", text="Client Interview"),
    LeverStage(id="stage-reference-check", text="Reference check"),
    LeverStage(id="offer", text="Offer"),
    LeverStage(id="stage-offer-declined", text="Offer Declined"),
]

_ARCHIVE_REASONS = [
    LeverArchiveReason(id="reason-hired", text="Hired", type="hired"),
    LeverArchiveReason(id="reason-withdrew", text="Withdrew", type=None),
    LeverArchiveReason(id="reason-position-closed", text="Position closed", type=None),
    LeverArchiveReason(id="reason-unresponsive", text="Unresponsive", type=None),
]

_USERS = [
    LeverUser(id="user-recruiter-1", name="Afraa Faleel", access_role="interviewer"),
    LeverUser(id="user-recruiter-2", name="Nifan Niyas", access_role="interviewer"),
]

_OPPORTUNITIES = [
    LeverOpportunity(
        id="opp-ron-axel-ppd",
        contact_id="contact-ron-axel",
        name="Ron Axel",
        email="ron.axel@example.com",
        headline="Senior Power Platform Developer",
        posting_id="post-senior-ppd",
        stage_id="stage-client-interview",
        stage_text="Client Interview",
        archived=False,
        created_at=_NOW - timedelta(days=14),
        updated_at=_NOW - timedelta(days=1),
        tags=["Power Platform", "Dataverse"],
        sources=["Added manually"],
        owner_user_id="user-recruiter-1",
        application_ids=["app-ron-axel-ppd-1"],
        stage_changes=[
            LeverStageChange(to_stage_id="lead-new", to_stage_index=0, updated_at=_NOW - timedelta(days=14)),
            LeverStageChange(
                to_stage_id="stage-client-interview", to_stage_index=10, updated_at=_NOW - timedelta(days=1)
            ),
        ],
    ),
    LeverOpportunity(
        id="opp-ron-axel-py",
        contact_id="contact-ron-axel",
        name="Ron Axel",
        email="ron.axel@example.com",
        headline="Senior Python Developer",
        posting_id="post-senior-py",
        stage_id="stage-recruiter-phone-screen",
        stage_text="Recruiter Phone Screen",
        archived=False,
        created_at=_NOW - timedelta(days=5),
        updated_at=_NOW - timedelta(hours=6),
        tags=["Python", "Django"],
        sources=["Job site"],
        owner_user_id="user-recruiter-1",
        application_ids=["app-ron-axel-py-1"],
        stage_changes=[
            LeverStageChange(to_stage_id="lead-new", to_stage_index=0, updated_at=_NOW - timedelta(days=5)),
            LeverStageChange(
                to_stage_id="stage-recruiter-phone-screen",
                to_stage_index=4,
                updated_at=_NOW - timedelta(hours=6),
            ),
        ],
    ),
]

_APPLICATIONS: dict[str, list[LeverApplication]] = {
    "opp-ron-axel-ppd": [
        LeverApplication(
            id="app-ron-axel-ppd-1", opportunity_id="opp-ron-axel-ppd", posting_id="post-senior-ppd",
            created_at=_NOW - timedelta(days=14),
        )
    ],
    "opp-ron-axel-py": [
        LeverApplication(
            id="app-ron-axel-py-1", opportunity_id="opp-ron-axel-py", posting_id="post-senior-py",
            created_at=_NOW - timedelta(days=5),
        )
    ],
}

_INTERVIEWS: dict[str, list[LeverInterview]] = {
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

_OFFERS: dict[str, list[LeverOfferSummary]] = {}


class MockLeverClient(LeverClient):
    """Realistic in-memory Lever data for local/demo use. Read-only, mirrors
    the shape of the real Lever API response objects it stands in for —
    including the real 14-stage pipeline confirmed by live tenant
    discovery. Deliberately excludes compensation/offer-document fields."""

    def list_postings(self) -> list[LeverPosting]:
        return list(_POSTINGS)

    def list_stages(self) -> list[LeverStage]:
        return list(_STAGES)

    def list_archive_reasons(self) -> list[LeverArchiveReason]:
        return list(_ARCHIVE_REASONS)

    def list_users(self) -> list[LeverUser]:
        return list(_USERS)

    def list_opportunities(
        self, posting_id: str | None = None, limit: int | None = None
    ) -> list[LeverOpportunity]:
        result = (
            list(_OPPORTUNITIES)
            if posting_id is None
            else [o for o in _OPPORTUNITIES if o.posting_id == posting_id]
        )
        return result[:limit] if limit is not None else result

    def get_opportunity(self, opportunity_id: str) -> LeverOpportunity | None:
        return next((o for o in _OPPORTUNITIES if o.id == opportunity_id), None)

    def list_applications(self, opportunity_id: str) -> list[LeverApplication]:
        return list(_APPLICATIONS.get(opportunity_id, []))

    def list_interviews(self, opportunity_id: str) -> list[LeverInterview]:
        return list(_INTERVIEWS.get(opportunity_id, []))

    def list_offers(self, opportunity_id: str) -> list[LeverOfferSummary]:
        return list(_OFFERS.get(opportunity_id, []))
