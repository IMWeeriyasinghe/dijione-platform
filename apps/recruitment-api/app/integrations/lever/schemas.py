"""Provider-shaped DTOs — mirror Lever's API vocabulary, not our domain
model. These must never be returned directly from DijiTalentFlow API
routes (CLAUDE.md §27); the mapping layer converts them into internal
DTOs/domain records.

Fields here reflect the real Dijital Team Lever tenant, confirmed by live
read-only discovery — not assumptions about what Lever generically
supports. Offer/compensation fields are deliberately NOT modeled here;
only lifecycle status/timestamps are (CLAUDE.md §60 discovery findings)."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LeverStageChange:
    to_stage_id: str
    to_stage_index: int | None
    updated_at: datetime
    user_id: str | None = None


@dataclass
class LeverPosting:
    id: str
    text: str
    state: str
    team: str = ""
    department: str = ""
    location: str = ""
    owner_user_id: str = ""
    hiring_manager_user_id: str = ""
    confidentiality: str = ""
    tags: list[str] = field(default_factory=list)
    archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class LeverStage:
    id: str
    text: str


@dataclass
class LeverArchiveReason:
    id: str
    text: str
    type: str | None = None  # "hired" | None (non-hired) per real tenant data
    status: str = "active"


@dataclass
class LeverUser:
    id: str
    name: str
    email: str = ""
    access_role: str = ""
    deactivated: bool = False


@dataclass
class LeverApplication:
    id: str
    opportunity_id: str
    posting_id: str | None
    posting_owner_user_id: str | None = None
    created_at: datetime | None = None


@dataclass
class LeverOfferSummary:
    """Deliberately excludes compensation, documents, and other sensitive
    offer fields — status/lifecycle only (CLAUDE.md §60 discovery)."""

    id: str
    posting_id: str | None
    status: str
    created_at: datetime | None = None


@dataclass
class LeverOpportunity:
    id: str
    # Real Lever data confirms `contact` is a separate, stable person
    # identifier distinct from the opportunity id — one Contact can back
    # multiple Opportunities. Candidate identity must be keyed off this,
    # never off the opportunity id.
    contact_id: str
    name: str
    email: str
    headline: str
    posting_id: str
    stage_id: str
    stage_text: str
    archived: bool
    created_at: datetime
    updated_at: datetime
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    owner_user_id: str | None = None
    sourced_by_user_id: str | None = None
    archive_reason_id: str | None = None
    application_ids: list[str] = field(default_factory=list)
    stage_changes: list[LeverStageChange] = field(default_factory=list)


@dataclass
class LeverInterview:
    id: str
    opportunity_id: str
    subject: str
    date: datetime
    feedback_status: str
