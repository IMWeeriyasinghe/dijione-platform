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
