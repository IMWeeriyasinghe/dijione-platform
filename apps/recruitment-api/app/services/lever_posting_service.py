"""Read-only ingestion of Lever Postings into the source read model.

    Lever GET API -> LeverClient -> Provider DTO -> Posting

GET-only (LeverClient is GET-only by construction). Never assigns a client
to anything — client trust is a DijiTalentFlow decision made separately
against this service's canonical posting DTO (which carries the parsed
governed DTC tag as a *fact*, not a resolution).
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.integrations.factory import get_lever_client
from app.integrations.lever.mock_client import FIXTURE_POSTING_IDS, MockLeverClient
from app.models.posting import Posting
from app.repositories.posting_repo import PostingRepository

logger = logging.getLogger("recruitment-api.lever_posting_service")


class MockSyncAgainstRealDataError(RuntimeError):
    """Raised when a mock-mode posting sync would write fixture data into a
    database that already holds real, live-synced postings."""


class LeverPostingSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.posting_repo = PostingRepository(db)

    def sync_postings(self) -> dict:
        client = get_lever_client()

        # Guard: the mock provider and the live provider write to the SAME
        # database (there is no per-mode DB separation). If someone flips a
        # live-synced local/dev DB back to INTEGRATIONS_MODE=mock and runs a
        # sync, the 3 mock fixtures get mixed in among the real postings and
        # surface as phantom "demo" rows. Refuse rather than contaminate —
        # use a disposable DATABASE_URL for isolated mock testing.
        if isinstance(client, MockLeverClient):
            real_count = self.posting_repo.count_outside(FIXTURE_POSTING_IDS)
            if real_count > 0:
                raise MockSyncAgainstRealDataError(
                    f"Refusing a mock-mode posting sync: this database already holds "
                    f"{real_count} non-fixture posting(s), i.e. real live-synced data. "
                    f"Point DATABASE_URL at a disposable file for mock testing, or run "
                    f"in live mode."
                )

        lever_postings = client.list_postings()

        created = 0
        updated = 0
        for lp in lever_postings:
            existing = self.posting_repo.get_by_lever_id(lp.id)
            if existing is None:
                self.posting_repo.add(
                    Posting(
                        lever_posting_id=lp.id,
                        title=lp.text,
                        state=lp.state,
                        team=lp.team,
                        department=lp.department,
                        location=lp.location,
                        owner_user_id=lp.owner_user_id,
                        hiring_manager_user_id=lp.hiring_manager_user_id,
                        confidentiality=lp.confidentiality,
                        tags=json.dumps(list(lp.tags)),
                        archived=lp.archived,
                        lever_created_at=lp.created_at,
                        lever_updated_at=lp.updated_at,
                        last_synced_at=datetime.now(UTC),
                    )
                )
                created += 1
            else:
                existing.title = lp.text
                existing.state = lp.state
                existing.team = lp.team
                existing.department = lp.department
                existing.location = lp.location
                existing.owner_user_id = lp.owner_user_id
                existing.hiring_manager_user_id = lp.hiring_manager_user_id
                existing.confidentiality = lp.confidentiality
                existing.tags = json.dumps(list(lp.tags))
                existing.archived = lp.archived
                existing.lever_created_at = lp.created_at
                existing.lever_updated_at = lp.updated_at
                existing.last_synced_at = datetime.now(UTC)
                updated += 1

        self.db.flush()
        logger.info(
            "Lever posting sync: created=%s updated=%s total=%s", created, updated, len(lever_postings)
        )
        return {"created": created, "updated": updated, "total": len(lever_postings)}
