from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageCreate(BaseModel):
    body: str


class MessageOut(BaseModel):
    id: int
    talent_request_id: int
    sender_id: int
    sender_name: str
    sender_role: str
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
