from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClientOut(BaseModel):
    id: int
    name: str
    industry: str | None
    account_manager: str | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientPortfolioOut(ClientOut):
    total_requests: int
    active_requests: int
    # Added for the Client Portfolios card uplift (plan §E) — how much of
    # this client's pipeline is actually moving, how much has actually
    # been shown to them, and when they were last engaged.
    active_application_count: int
    client_visible_count: int
    latest_request_at: datetime | None
