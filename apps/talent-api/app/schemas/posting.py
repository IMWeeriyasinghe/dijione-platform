from datetime import datetime

from pydantic import BaseModel, Field


class PostingOut(BaseModel):
    """Full Posting record with mapping diagnostics — internal/staff view
    only. Diagnostic fields (tags/team/department) are shown here for
    human review but must never be treated as authorization evidence."""

    id: int
    lever_posting_id: str
    title: str
    state: str
    team: str
    department: str
    location: str
    confidentiality: str
    tags: list[str] = Field(default_factory=list)
    archived: bool
    lever_created_at: datetime | None
    lever_updated_at: datetime | None
    last_synced_at: datetime | None

    mapping_status: str
    mapping_client_id: int | None
    mapping_client_name: str | None = None
    mapping_source: str
    mapping_verified_at: datetime | None


class ClientSafePostingOut(BaseModel):
    """Posting DTO for a client caller — only ever reachable once the
    Posting's PostingClientMapping is VERIFIED for that exact client_id.
    No raw tags, team, department, or mapping-internal fields."""

    id: int
    title: str
    location: str
    state: str


class PostingClientMappingVerify(BaseModel):
    client_id: int
