"""Provider-shaped DTOs — mirror Lever's API vocabulary, not our domain
model. These must never be returned directly from DijiTalentFlow API
routes (CLAUDE.md §27); the mapping layer converts them into internal
DTOs/domain records."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LeverPosting:
    id: str
    text: str
    state: str


@dataclass
class LeverStage:
    id: str
    text: str


@dataclass
class LeverOpportunity:
    id: str
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


@dataclass
class LeverInterview:
    id: str
    opportunity_id: str
    subject: str
    date: datetime
    feedback_status: str
