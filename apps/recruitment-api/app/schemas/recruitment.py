from __future__ import annotations

from pydantic import BaseModel


class DtcTagFact(BaseModel):
    """The governed ``DTC - <Client Name>`` posting tag parsed as a provider
    fact. Recruitment Source parses; DijiTalentFlow decides trust/visibility
    (it never fuzzy-matches, and anything but ``OK`` must fail closed)."""

    status: str  # NO_TAG | OK | MALFORMED | MULTIPLE
    client_name: str | None = None
    raw_tag: str | None = None
    raw_tags: list[str] = []


class PostingOut(BaseModel):
    provider: str = "LEVER"
    external_id: str            # Lever posting id — the stable cross-service key
    title: str
    state: str
    team: str
    department: str
    location: str
    confidentiality: str
    tags: list[str]
    archived: bool
    dtc_tag: DtcTagFact
    lever_created_at: str | None = None
    lever_updated_at: str | None = None
    synced_at: str | None = None


class CandidacyOut(BaseModel):
    provider: str = "LEVER"
    external_id: str            # Lever opportunity id
    posting_external_id: str
    candidate_external_id: str  # Lever contact id
    candidate_name: str
    candidate_email: str
    candidate_headline: str
    current_stage: str
    status: str
    lever_archive_reason: str | None = None
    synced_at: str | None = None


class SyncRequestIn(BaseModel):
    requested_by_application: str = "talent-flow"
    requested_by_user_id: int | None = None


class SyncRunOut(BaseModel):
    run_id: str
    provider: str
    status: str
    trigger_type: str
    requested_by_application: str
    requested_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    records_read: int
    records_created: int
    records_updated: int
    records_unchanged: int
    error_summary: str | None = None


class SyncAcceptedOut(BaseModel):
    run_id: str
    status: str
    started: bool
    message: str


class FreshnessOut(BaseModel):
    provider: str
    last_successful_sync_at: str | None = None
    latest_run: SyncRunOut | None = None
