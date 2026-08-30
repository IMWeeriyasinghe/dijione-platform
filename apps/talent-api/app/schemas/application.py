from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationCreate(BaseModel):
    candidate_id: int
    talent_request_id: int
    current_stage: str = "SOURCING"


class ApplicationStageUpdate(BaseModel):
    # Canonical request field is `stage` — the handler, the service method
    # parameter, and the frontend (`updateApplicationStage`) all use `stage`.
    # (Was `current_stage`, which never matched the handler or the client and
    # made this endpoint always 422 — see docs/talent-flow/authorization-review.md.)
    stage: str


class ApplicationStatusUpdate(BaseModel):
    status: str
    rejection_reason: str = ""


class ApplicationScoreUpdate(BaseModel):
    score: float
    recruiter_notes: str = ""


class ApplicationVisibilityUpdate(BaseModel):
    is_client_visible: bool
    client_visible_notes: str = ""


class ApplicationOut(BaseModel):
    id: int
    candidate_id: int
    candidate_name: str
    talent_request_id: int
    client_name: str
    designation: str
    current_stage: str
    status: str
    score: float | None
    recruiter_notes: str
    client_visible_notes: str
    rejection_reason: str
    is_client_visible: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
