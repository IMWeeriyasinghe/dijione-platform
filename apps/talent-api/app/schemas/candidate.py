from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CandidateApplicationSummary(BaseModel):
    application_id: int
    client_name: str
    designation: str
    current_stage: str
    status: str


class CandidateOut(BaseModel):
    """Full candidate record — Talent Acquisition view only."""

    id: int
    full_name: str
    email: str
    phone: str
    professional_title: str
    summary: str
    location: str
    availability_status: str
    skills: list[str]
    cv_reference: str
    source: str
    applications: list[CandidateApplicationSummary]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientSafeCandidateOut(BaseModel):
    """Candidate DTO filtered for client visibility (CLAUDE.md §35).

    Never includes recruiter notes, scores, other-client applications, or
    unrestricted CV content.
    """

    application_id: int
    full_name: str
    professional_title: str
    skills: list[str]
    relevant_experience_summary: str
    current_stage: str
    upcoming_interview_status: str | None


class CandidateCreate(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    professional_title: str = ""
    summary: str = ""
    location: str = ""
    skills: list[str] = Field(default_factory=list)
    source: str = "MANUAL"
