from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    talent_request_id: int
    file_name: str
    category: str = "OTHER"
    storage_reference: str = ""


class DocumentOut(BaseModel):
    id: int
    talent_request_id: int
    file_name: str
    category: str
    uploaded_by: int
    uploaded_by_name: str
    storage_reference: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
