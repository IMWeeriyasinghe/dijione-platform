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
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx
from auth_client_py import RecruitmentSourceClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.services.audit_service import AuditService
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler
from app.services.side_effects import SideEffect, collect_side_effects, deliver_side_effects
from app.services.verified_posting_promotion_reconciler import (
    CANDIDACY_PAGE_LIMIT,
    VerifiedPostingPromotionReconciler,
)

logger = logging.getLogger("talent-api.recruitment_consumer")


# Browser-facing calls fail fast. Scheduled reconciliation usually reaches a
# recruitment-api that has scaled to zero: measured cold starts run to 47 s
# before readiness probing, so the batch path has to wait that out.
INTERACTIVE_SOURCE_TIMEOUT_SECONDS = 5.0
BATCH_SOURCE_TIMEOUT_SECONDS = 90.0
# Container Apps ends an HTTP request at 240 s. Stop short of that so a slow
# run rolls back and reports FAILED instead of being cut off at the ingress.
RECONCILE_BUDGET_SECONDS = 220.0
SIDE_EFFECT_DELIVERY_SECONDS = 200.0
# Bound each PostgreSQL statement and lock wait inside the reconcile.
_POSTGRES_STATEMENT_TIMEOUT = "60s"
_POSTGRES_LOCK_TIMEOUT = "15s"
# Bounds one posting's read: 20,000 candidacies, against 2,090 at most today.
CANDIDACY_MAX_PAGES = 40

OUTCOME_SUCCEEDED = "SUCCEEDED"
OUTCOME_PARTIAL = "PARTIAL"
OUTCOME_SKIPPED = "SKIPPED"
OUTCOME_FAILED = "FAILED"

# Arbitrary fixed key, unique to this operation within the talent database.
_RECONCILE_ADVISORY_LOCK_KEY = 7310482615
_local_reconcile_lock = threading.Lock()


class ReconcileBudgetExceeded(Exception):
    """The run outlived RECONCILE_BUDGET_SECONDS; nothing may be committed."""


class CandidacyReadIncomplete(Exception):
    """A posting's candidacies could not be proven fully read."""


class PagedRecruitmentClient(RecruitmentSourceClient):
    def list_candidacies_page(
        self, *, posting_external_id: str, after_external_id: str, limit: int
    ) -> list[dict]:
        return self._get("/api/recruitment/candidacies", params={
            "posting_external_id": posting_external_id, "after_external_id": after_external_id, "limit": limit,
        }).json()


def read_all_candidacies(
    client: PagedRecruitmentClient, posting_external_id: str, on_page: Callable[[], None]
) -> list[dict]:
    """Every candidacy of one posting, or an exception. Only an empty page ends
    the read, so a full last page is not mistaken for more or for the end, and a
    source that repeats rows (one without paging) is refused, not truncated."""
    rows: list[dict] = []
    seen: set[str] = set()
    after = ""
    for _ in range(CANDIDACY_MAX_PAGES + 1):
        page = client.list_candidacies_page(
            posting_external_id=posting_external_id, after_external_id=after, limit=CANDIDACY_PAGE_LIMIT
        )
        if not page:
            return rows
        if len(page) > CANDIDACY_PAGE_LIMIT:
            raise CandidacyReadIncomplete("oversized_page")
        for row in page:
            external_id = row.get("external_id")
            if not external_id or external_id in seen or row.get("posting_external_id") != posting_external_id:
                raise CandidacyReadIncomplete("unexpected_row")
            seen.add(external_id)
        rows.extend(page)
        after = page[-1]["external_id"]
        on_page()
    raise CandidacyReadIncomplete("page_limit")


def _build_client(timeout: float) -> PagedRecruitmentClient:
    settings = get_settings()
    return PagedRecruitmentClient(
        base_url=settings.recruitment_api_url,
        internal_secret=settings.internal_service_secret,
        timeout=timeout,
        caller="talent-api",
    )


def get_recruitment_client() -> PagedRecruitmentClient:
    return _build_client(INTERACTIVE_SOURCE_TIMEOUT_SECONDS)


def get_recruitment_batch_client() -> PagedRecruitmentClient:
    return _build_client(BATCH_SOURCE_TIMEOUT_SECONDS)


@contextmanager
def reconcile_guard(db: Session) -> Iterator[bool]:
    """Single-flight across replicas. On PostgreSQL this is a transaction
    advisory lock in the reconcile's own transaction, so it is released by
    its commit or rollback, or by the database if the replica dies. SQLite
    (local and tests) has no equivalent and uses a process-local lock."""
    if db.get_bind().dialect.name == "postgresql":
        acquired = bool(
            db.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": _RECONCILE_ADVISORY_LOCK_KEY},
            ).scalar()
        )
        try:
            if acquired:
                db.execute(text(f"SET LOCAL statement_timeout = '{_POSTGRES_STATEMENT_TIMEOUT}'"))
                db.execute(text(f"SET LOCAL lock_timeout = '{_POSTGRES_LOCK_TIMEOUT}'"))
            yield acquired
        finally:
            db.rollback()
        return

    acquired = _local_reconcile_lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        db.rollback()
        if acquired:
            _local_reconcile_lock.release()


_UPSTREAM_HOLD_REASONS = {
    "RUNNING": "upstream_running",
    "NONE": "upstream_never_synced",
    "FAILED": "upstream_failed",
    "STALE": "upstream_stale",
    "INCOMPLETE": "upstream_incomplete",
}


def upstream_hold(client: RecruitmentSourceClient) -> tuple[str | None, dict]:
    """Why this reconcile must not read the source yet, or None. Anything other
    than an explicit COMPLETE holds it: reconcile applies mapping changes, so it
    only ever acts on a full read."""
    try:
        snapshot = client.get_freshness().get("source_snapshot") or {}
    except httpx.HTTPError:
        return "source_unavailable", {}
    state = snapshot.get("state")
    if state == "COMPLETE":
        return None, snapshot
    return _UPSTREAM_HOLD_REASONS.get(state, "upstream_incomplete"), snapshot


def _deliver_now(deliver: Callable[..., None], *args, **kwargs) -> None:
    deliver(*args, **kwargs)


def classify_reconcile_result(result: dict) -> tuple[str, list[str]]:
    """Only a complete read of the source is SUCCEEDED."""
    if not result.get("refreshed"):
        return OUTCOME_FAILED, [result.get("reason", "unknown")]
    reasons: list[str] = []
    if not result["postings_seen"]:
        reasons.append("no_postings")
    return (OUTCOME_PARTIAL, reasons) if reasons else (OUTCOME_SUCCEEDED, [])


def run_reconcile(
    db: Session,
    *,
    client: RecruitmentSourceClient | None = None,
    budget_seconds: float | None = None,
    schedule_delivery: Callable[..., None] | None = None,
) -> dict:
    """Run one guarded reconcile and report what actually happened. The body
    holds aggregate counts only, and logs name the exception type only, so
    neither can carry candidate data. Audit and notification calls are sent
    only after a commit, so a rolled-back run produces none."""
    started = time.monotonic()
    result: dict = {}
    effects: list[SideEffect] = []
    with collect_side_effects() as collected, reconcile_guard(db) as acquired:
        if not acquired:
            outcome, reasons = OUTCOME_SKIPPED, ["already_running"]
        else:
            try:
                service = RecruitmentConsumerService(db, client=client)
                hold, snapshot = upstream_hold(service.client)
                if hold:
                    outcome = OUTCOME_FAILED if hold == "source_unavailable" else OUTCOME_SKIPPED
                    reasons = [hold]
                    result = {"upstream": snapshot}
                else:
                    result = service.refresh_projection_and_reconcile(budget_seconds=budget_seconds)
                    outcome, reasons = classify_reconcile_result(result)
                    if outcome == OUTCOME_SUCCEEDED and snapshot.get("latest_run_status") != "SUCCEEDED" and (
                        "latest_run_status" in snapshot
                    ):
                        # Every posting is current, but across several runs.
                        outcome, reasons = OUTCOME_PARTIAL, ["upstream_rolling_read"]
                    if result.get("refreshed"):
                        effects = collected
            except Exception as exc:  # noqa: BLE001 - reported, rolled back by the guard
                outcome, reasons = OUTCOME_FAILED, [type(exc).__name__]

    if effects:
        (schedule_delivery or _deliver_now)(
            deliver_side_effects, effects, limit_seconds=SIDE_EFFECT_DELIVERY_SECONDS
        )

    if "upstream" in result:
        _audit_hold(reasons[0], result["upstream"])

    elapsed = round(time.monotonic() - started, 1)
    if outcome != OUTCOME_SUCCEEDED:
        logger.warning(
            "recruitment reconcile outcome=%s reasons=%s elapsed_seconds=%s",
            outcome, ",".join(reasons), elapsed,
        )
    return {
        "outcome": outcome,
        "fully_refreshed": outcome == OUTCOME_SUCCEEDED,
        "reasons": reasons,
        "elapsed_seconds": elapsed,
        "counts": {k: v for k, v in result.items() if k not in ("refreshed", "reason")},
    }


def _audit_hold(reason: str, snapshot: dict) -> None:
    try:
        AuditService().log(
            actor_id=None, action="recruitment.reconcile_held", entity_type="RecruitmentReconcile",
            entity_id=0, new_state={"reason": reason, **snapshot},
        )
    except Exception:  # noqa: BLE001 - best-effort, the outcome is still reported
        logger.debug("reconcile hold audit skipped", exc_info=True)


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

    def refresh_projection_and_reconcile(self, *, budget_seconds: float | None = None) -> dict:
        """Pull the current canonical postings from recruitment-api, refresh
        the local projection, and run the DTC trust reconciliation. On a
        source-domain outage this is a no-op that keeps the last-good
        projection and never widens visibility. The whole refresh is one
        transaction, committed only at the end; past ``budget_seconds`` it
        raises before committing, and a candidacy read that fails or cannot
        be proven complete rolls the whole of it back."""
        started = time.monotonic()

        def check_budget() -> None:
            if budget_seconds is not None and time.monotonic() - started > budget_seconds:
                raise ReconcileBudgetExceeded

        try:
            postings = self.client.list_postings()
        except httpx.HTTPError as exc:
            logger.warning(
                "recruitment-api unavailable — projection not refreshed (%s)", type(exc).__name__
            )
            return {"refreshed": False, "reason": "source_unavailable"}

        summary = PostingClientMappingReconciler(self.db).reconcile_postings(postings)
        check_budget()

        try:
            candidacies: list[dict] = []
            # Per posting, so candidacies for postings TalentFlow ignores are
            # never read. All or nothing: one unproven posting discards them all.
            for mapping in PostingClientMappingRepository(self.db).list_verified():
                candidacies.extend(read_all_candidacies(self.client, mapping.posting_external_id, check_budget))
        except (httpx.HTTPError, CandidacyReadIncomplete) as exc:
            # Nothing commits on an unproven read, including the mapping changes
            # above, and run_reconcile drops their audit calls with the rollback.
            logger.warning(
                "recruitment-api candidacies unavailable — nothing applied (%s)", type(exc).__name__
            )
            self.db.rollback()
            return {"refreshed": False, "reason": "candidacies_unavailable"}
        promotion = VerifiedPostingPromotionReconciler(self.db).reconcile(candidacies=candidacies)

        check_budget()
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
            "promotion": {
                "verified_postings": promotion.verified_postings,
                "talent_requests_created": promotion.talent_requests_created,
                "talent_requests_updated": promotion.talent_requests_updated,
                "candidates_created": promotion.candidates_created,
                "candidates_updated": promotion.candidates_updated,
                "applications_created": promotion.applications_created,
                "applications_updated": promotion.applications_updated,
                "candidacies_seen": promotion.candidacies_seen,
                "candidacies_skipped_no_verified_request": (
                    promotion.candidacies_skipped_no_verified_request
                ),
                "collapsed_duplicate_candidacies": promotion.collapsed_duplicate_candidacies,
                "requests_retired": promotion.requests_retired,
                "requests_access_withdrawn": promotion.requests_access_withdrawn,
                "unchanged": promotion.unchanged,
            },
        }
