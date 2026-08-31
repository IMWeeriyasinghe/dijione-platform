"""DijiTalentFlow's consumer of the Recruitment Source domain.

talent-api holds NO Lever client and NO Lever credential (Architecture
Completion Plan §3). It calls recruitment-api over the
``RecruitmentSourceClient`` HTTP contract and keeps a thin local
``RecruitmentPostingRef`` projection so the fail-closed client-visibility
join and the staff review screen keep working when recruitment-api is
briefly unavailable.
"""

from __future__ import annotations

import logging

import httpx
from auth_client_py import RecruitmentSourceClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler

logger = logging.getLogger("talent-api.recruitment_consumer")


def get_recruitment_client() -> RecruitmentSourceClient:
    settings = get_settings()
    return RecruitmentSourceClient(
        base_url=settings.recruitment_api_url,
        internal_secret=settings.internal_service_secret,
        timeout=5.0,
        caller="talent-api",
    )


class RecruitmentConsumerService:
    def __init__(self, db: Session, client: RecruitmentSourceClient | None = None):
        self.db = db
        self.client = client or get_recruitment_client()

    def freshness(self) -> dict:
        """Proxy recruitment-api freshness; degrade to a stale marker if the
        source domain is unreachable (never raises to the browser)."""
        try:
            return {"available": True, **self.client.get_freshness()}
        except httpx.HTTPError as exc:
            logger.warning("recruitment-api freshness unavailable: %s", type(exc).__name__)
            return {"available": False, "provider": "LEVER", "last_successful_sync_at": None}

    def request_sync(self, *, requested_by_user_id: int | None) -> dict:
        """Proxy an authorized ad-hoc sync request to recruitment-api (which
        runs it async, 202). The staff-scope check has already happened in
        the route. Raises ``httpx.HTTPError`` for the route to translate."""
        return self.client.request_sync(
            requested_by_user_id=requested_by_user_id, requested_by_application="talent-flow"
        )

    def refresh_projection_and_reconcile(self) -> dict:
        """Pull the current canonical postings from recruitment-api, refresh
        the local projection, and run the DTC trust reconciliation. On a
        source-domain outage this is a no-op that keeps the last-good
        projection — it never raises and never widens visibility."""
        try:
            postings = self.client.list_postings()
        except httpx.HTTPError as exc:
            logger.warning(
                "recruitment-api unavailable — projection not refreshed (%s)", type(exc).__name__
            )
            return {"refreshed": False, "reason": "source_unavailable"}

        summary = PostingClientMappingReconciler(self.db).reconcile_postings(postings)
        self.db.commit()
        return {
            "refreshed": True,
            "postings_seen": summary.refs_upserted,
            "resolved": summary.resolved,
            "reassigned": summary.reassigned,
            "reverted": summary.reverted,
            "conflicts": summary.conflicts,
            "unknown": summary.unknown,
            "ambiguous": summary.ambiguous,
            "malformed": summary.malformed,
            "no_tag": summary.no_tag,
        }
