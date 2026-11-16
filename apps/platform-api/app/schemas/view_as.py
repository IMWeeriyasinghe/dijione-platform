from datetime import datetime

from pydantic import BaseModel


class ViewAsStartIn(BaseModel):
    target_user_id: int


class ViewAsTargetOut(BaseModel):
    id: int
    full_name: str
    email: str
    title: str | None = None


class ViewAsStartOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    session_id: str
    expires_at: datetime
    target: ViewAsTargetOut


class ViewAsInfoOut(BaseModel):
    """Carried on ``/api/auth/me`` while a View-as token is in use, so every application can show
    the banner."""

    session_id: str
    expires_at: datetime
    actor_id: int
    actor_name: str
    read_only: bool = True


class ViewAsEndOut(BaseModel):
    session_id: str
    ended: bool
