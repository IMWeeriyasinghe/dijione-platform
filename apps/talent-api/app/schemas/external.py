from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RedeemRequest(BaseModel):
    # The raw magic-link token, read by the SPA from the URL fragment and
    # POSTed here. Never appears in a query string, a path, or a log.
    token: str = Field(min_length=1, max_length=512)


class RedeemResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the session JWT expires


# --- TA grant management (staff-authenticated) --------------------------


class GrantCreateRequest(BaseModel):
    client_id: int
    contact_name: str = Field(default="", max_length=255)
    contact_email: str = Field(default="", max_length=255)
    # None → the configured default (14 days). Bounded so a TA cannot mint
    # an effectively-indefinite link (plan B.5: "No indefinite grants").
    expires_in_days: int | None = Field(default=None, ge=1, le=90)
    # An explicit expiry date picker (plan §H2) sends this instead of a day
    # count — a TA thinks in "expires on <date>", not "in N days". When
    # both are given, expires_at wins. Bounds (now+[1,90]d) are enforced in
    # MagicLinkService.create_grant, where "now" is meaningful — a Field
    # constraint here can't see the current time.
    expires_at: datetime | None = None


class GrantExtendRequest(BaseModel):
    """Extend-only: moves expires_at forward, never back — shortening is
    what Revoke is for. Same now+[1,90]d bound as create; also validated
    against the grant's *current* expires_at in the service."""

    expires_at: datetime | None = None
    expires_in_days: int | None = Field(default=None, ge=1, le=90)


class GrantOut(BaseModel):
    """Admin view of a grant — never the raw token, only its non-secret
    prefix. ``status`` is derived (ACTIVE / EXPIRED / REVOKED)."""

    public_id: str
    client_id: int
    client_name: str
    scope_type: str
    contact_name: str
    contact_email: str
    token_prefix: str
    status: str
    issued_by_user_id: int
    issued_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None
    last_used_at: datetime | None
    use_count: int
    revoked_at: datetime | None
    revoked_by_user_id: int | None


class GrantCreatedOut(GrantOut):
    """Returned once, from create/regenerate only — carries the raw token
    and the one-time access URL. Never persisted, never returned again."""

    raw_token: str
    access_url: str
