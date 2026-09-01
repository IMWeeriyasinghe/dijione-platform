from __future__ import annotations

from pydantic import BaseModel, Field


class RedeemRequest(BaseModel):
    # The raw magic-link token, read by the SPA from the URL fragment and
    # POSTed here. Never appears in a query string, a path, or a log.
    token: str = Field(min_length=1, max_length=512)


class RedeemResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the session JWT expires
