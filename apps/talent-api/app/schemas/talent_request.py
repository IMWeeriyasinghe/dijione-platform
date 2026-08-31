from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class StageProgressOut(BaseModel):
    stage: str
    label: str
    state: str  # DONE | CURRENT | UPCOMING


class TalentRequestBase(BaseModel):
    designation: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8000)
    required_skills: list[str] = Field(default_factory=list)
    seniority: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=200)
    engagement_type: str = "FULL_TIME"
    target_start_date: date | None = None
    notes: str = Field(default="", max_length=4000)


class TalentRequestCreate(TalentRequestBase):
    pass


class TalentRequestOut(BaseModel):
    id: int
    request_code: str
    client_id: int
    client_name: str | None = None
    designation: str
    description: str
    required_skills: list[str]
    seniority: str
    location: str
    engagement_type: str
    target_start_date: date | None
    notes: str
    current_stage: str
    lifecycle_status: str
    customer_success_status: str
    ta_status: str
    client_safe_status_text: str
    priority: str
    progress_percent: int
    stage_timeline: list[StageProgressOut]
    active_application_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TalentRequestReviewDecision(BaseModel):
    decision: str  # APPROVED | REJECTED | CLARIFICATION_REQUIRED
    reason: str = ""


class TalentRequestStageUpdate(BaseModel):
    stage: str
    client_safe_status_text: str | None = None


class TalentRequestTaStatusUpdate(BaseModel):
    ta_status: str
