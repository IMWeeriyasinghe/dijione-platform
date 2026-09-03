from pydantic import BaseModel

from app.schemas.talent_request import TalentRequestOut


class ClientDashboardOut(BaseModel):
    client_name: str
    active_requests: int
    candidates_in_process: int
    interviews_this_week: int
    offers_in_progress: int
    requests: list[TalentRequestOut]


class TaDashboardOut(BaseModel):
    clients: int
    active_requests: int
    active_applications: int
    available_candidates: int
    interviews_scheduled: int
    offers_in_progress: int
    pending_review_count: int
    attention_requests: list[TalentRequestOut]
