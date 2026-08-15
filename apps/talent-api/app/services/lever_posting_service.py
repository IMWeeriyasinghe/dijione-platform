"""Read-only ingestion of Lever Postings into the local read model.

INITIAL / RECONCILIATION READ path (CLAUDE.md §60 architecture):

    Lever GET API -> LeverClient -> Provider DTO -> mapper -> Posting +
    PostingClientMapping (created UNMAPPED if new) -> DijiTalentFlow read
    model.

This never writes to Lever (LeverClient is GET-only by construction) and
never assigns a client — every newly-ingested Posting gets a
PostingClientMapping row with status=UNMAPPED, client_id=None. Resolving
that mapping is a separate, explicit action (see talent_postings.py's
verify-mapping route), never inferred here from tags/title text.
"""

import logging

from sqlalchemy.orm import Session

from app.core.constants import PostingClientMappingStatus
from app.integrations.factory import get_lever_client
from app.models.posting import Posting
from app.models.posting_client_mapping import PostingClientMapping
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.repositories.posting_repo import PostingRepository

logger = logging.getLogger("app.services.lever_posting_service")


class LeverPostingSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.posting_repo = PostingRepository(db)
        self.mapping_repo = PostingClientMappingRepository(db)

    def sync_postings(self) -> dict:
        client = get_lever_client()
        lever_postings = client.list_postings()

        created = 0
        updated = 0
        for lp in lever_postings:
            existing = self.posting_repo.get_by_lever_id(lp.id)
            if existing is None:
                posting = Posting(
                    lever_posting_id=lp.id,
                    title=lp.text,
                    state=lp.state,
                    team=lp.team,
                    department=lp.department,
                    location=lp.location,
                    owner_user_id=lp.owner_user_id,
                    hiring_manager_user_id=lp.hiring_manager_user_id,
                    confidentiality=lp.confidentiality,
                    tags=_encode_tags(lp.tags),
                    archived=lp.archived,
                    lever_created_at=lp.created_at,
                    lever_updated_at=lp.updated_at,
                    last_synced_at=_now(),
                )
                self.posting_repo.add(posting)
                self.mapping_repo.add(
                    PostingClientMapping(
                        posting_id=posting.id,
                        status=PostingClientMappingStatus.UNMAPPED.value,
                    )
                )
                created += 1
            else:
                # Pure source-data overwrite — never touches
                # PostingClientMapping (separate table, separate row).
                existing.title = lp.text
                existing.state = lp.state
                existing.team = lp.team
                existing.department = lp.department
                existing.location = lp.location
                existing.owner_user_id = lp.owner_user_id
                existing.hiring_manager_user_id = lp.hiring_manager_user_id
                existing.confidentiality = lp.confidentiality
                existing.tags = _encode_tags(lp.tags)
                existing.archived = lp.archived
                existing.lever_created_at = lp.created_at
                existing.lever_updated_at = lp.updated_at
                existing.last_synced_at = _now()
                updated += 1

        self.db.flush()
        logger.info("Lever posting sync: created=%s updated=%s total=%s", created, updated, len(lever_postings))
        return {"created": created, "updated": updated, "total": len(lever_postings)}


def _encode_tags(tags: list[str]) -> str:
    import json

    return json.dumps(list(tags))


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
