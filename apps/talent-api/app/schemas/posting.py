from datetime import datetime

from pydantic import BaseModel


class PostingOut(BaseModel):
    """Full posting-review record — internal/staff view only. The posting
    facts are a cached projection of recruitment-api's canonical DTO; the
    mapping fields are the DijiTalentFlow-owned trust decision. Diagnostic
    fields must never be treated as authorization evidence."""

    id: int                       # local RecruitmentPostingRef id
    external_id: str              # stable provider (Lever) posting id
    provider: str = "LEVER"
    title: str
    state: str
    location: str
    archived: bool
    source_synced_at: datetime | None = None
    lever_created_at: datetime | None = None

    mapping_status: str
    mapping_client_id: int | None
    mapping_client_name: str | None = None
    mapping_source: str
    mapping_verified_at: datetime | None = None

    # Governed DTC posting-tag reconciliation (diagnostic / staff review).
    dtc_source_tag: str | None = None
    dtc_client_name: str | None = None
    resolution_status: str = "NO_DTC_TAG"


class ClientSafePostingOut(BaseModel):
    """Posting DTO for a client caller — only ever reachable once the
    posting's PostingClientMapping is VERIFIED for that exact client_id.
    No raw tags, mapping-internal fields, or source diagnostics."""

    id: int
    title: str
    location: str
    state: str


class PostingClientMappingVerify(BaseModel):
    client_id: int
