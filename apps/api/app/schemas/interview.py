from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InterviewCreate(BaseModel):
    application_id: int
    scheduled_at: datetime
    interview_type: str = "CLIENT_INTERVIEW"
    meeting_link: str = ""
    client_visible: bool = True
    notes: str = ""


class InterviewStatusUpdate(BaseModel):
    status: str
    notes: str = ""


class InterviewOut(BaseModel):
    id: int
    application_id: int
    talent_request_id: int
    candidate_name: str
    client_name: str
    designation: str
    scheduled_at: datetime
    interview_type: str
    status: str
    meeting_link: str
    client_visible: bool
    notes: str

    model_config = ConfigDict(from_attributes=True)


class ClientInterviewOut(BaseModel):
    id: int
    talent_request_id: int
    candidate_name: str
    designation: str
    scheduled_at: datetime
    interview_type: str
    status: str
    meeting_link: str | None
