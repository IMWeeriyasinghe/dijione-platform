import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Deliberately a regex, not pydantic's EmailStr — avoids adding the
# email-validator dependency for a single input field. Not RFC-5322-complete;
# it exists to reject obvious typos/garbage, not to be an email verifier.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(max_length=254)
    phone: str = Field(default="", max_length=40)
    professional_title: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=200)
    skills: list[str] = Field(default_factory=list)
    source: str = "MANUAL"

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("email must be a valid email address")
        return v
