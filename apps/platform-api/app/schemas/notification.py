from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    is_read: bool
    related_entity_type: str | None
    related_entity_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
