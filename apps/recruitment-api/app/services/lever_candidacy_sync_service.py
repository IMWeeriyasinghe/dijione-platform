"""Read-only ingestion of Lever Contacts/Opportunities into the source read
model — ``RecruitmentCandidate`` (contact facts) + ``RecruitmentCandidacy``
(Opportunity linking a contact to a Posting).

    Lever GET API -> LeverClient -> Provider DTOs -> mapper ->
    RecruitmentCandidate + ExternalMapping + RecruitmentCandidacy

GET-only. Never assigns a client — a candidacy resolves to a client-visible
Application only through a separate DijiTalentFlow step against a VERIFIED
PostingClientMapping (not here, not this service).
"""

import json
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.constants import ApplicationStatus
from app.integrations.factory import get_lever_client
from app.integrations.lever.mapper import map_lever_archive_outcome, map_lever_stage
from app.models.external_mapping import ExternalMapping
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.models.recruitment_candidate import RecruitmentCandidate
from app.recruitment_source.dtc import DtcParseStatus, parse_dtc
from app.repositories.candidacy_repo import (
    RecruitmentCandidacyRepository,
    RecruitmentCandidateRepository,
)
from app.repositories.integration_repo import ExternalMappingRepository
from app.repositories.posting_repo import PostingRepository

logger = logging.getLogger("recruitment-api.lever_candidacy_sync_service")

_PROVIDER = "LEVER"
_CONTACT_TYPE = "contact"
# Separate budgets: the general pass makes one Lever call per opportunity and
# must not be able to starve the client-posting reads.
_GENERAL_READ_BUDGET_SECONDS = 300.0
_DTC_READ_BUDGET_SECONDS = 600.0
# Stop early when Lever keeps refusing, rather than spending the whole budget.
_MAX_CONSECUTIVE_POSTING_FAILURES = 3
# A client posting read longer ago than this no longer counts as current. Eight
# 6-hourly runs, so a backlog can finish before its earliest reads expire.
SNAPSHOT_MAX_AGE = timedelta(hours=48)
# Just under the 6-hour schedule: scheduled runs refresh every posting, while
# an extra run soon after a good one does not read it again.
_REREAD_AFTER = timedelta(hours=5)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def dtc_postings(posting_repo: PostingRepository) -> list:
    return [
        p for p in posting_repo.list_all()
        if parse_dtc(json.loads(p.tags or "[]")).status != DtcParseStatus.NO_TAG
    ]


def unread_postings(postings: list, now: datetime) -> list:
    return [
        p for p in postings
        if p.dtc_last_read_at is None or now - _aware(p.dtc_last_read_at) >= SNAPSHOT_MAX_AGE
    ]


def _is_current(posting, now: datetime) -> bool:
    return posting.dtc_last_read_at is not None and now - _aware(posting.dtc_last_read_at) < _REREAD_AFTER


def _read_order(posting) -> tuple:
    """Never attempted first, then least recently attempted, so a posting that
    keeps failing cannot hold back the others."""
    attempted = posting.dtc_last_attempt_at
    return (attempted is not None, _aware(attempted) if attempted else datetime.min.replace(tzinfo=UTC), posting.id)


class LeverCandidacySyncService:
    def __init__(self, db: Session):
        self.db = db
        self.mapping_repo = ExternalMappingRepository(db)
        self.posting_repo = PostingRepository(db)
        self.candidate_repo = RecruitmentCandidateRepository(db)
        self.candidacy_repo = RecruitmentCandidacyRepository(db)

    def sync_opportunities(self, limit: int | None = None) -> dict:
        started = time.monotonic()
        client = get_lever_client()

        stage_text_by_id = {s.id: s.text for s in client.list_stages()}
        archive_reason_text_by_id = {r.id: r.text for r in client.list_archive_reasons()}

        opportunities = client.list_opportunities(limit=limit)
        limit_reached = limit is not None and len(opportunities) >= limit

        candidates_created = 0
        candidates_matched = 0
        candidacies_created = 0
        candidacies_updated = 0
        skipped_no_local_posting = 0

        seen_ids: set[str] = set()
        general_budget_exhausted = False
        for opp in opportunities:
            if time.monotonic() - started > _GENERAL_READ_BUDGET_SECONDS:
                general_budget_exhausted = True
                logger.warning("Lever general opportunity read stopped at its budget")
                break
            seen_ids.add(opp.id)
            candidate, created = self._resolve_candidate(opp)
            candidates_created += int(created)
            candidates_matched += int(not created)

            applications = client.list_applications(opp.id)
            lever_posting_id = applications[0].posting_id if applications else None
            local_posting = (
                self.posting_repo.get_by_lever_id(lever_posting_id)
                if lever_posting_id
                else None
            )
            if local_posting is None:
                skipped_no_local_posting += 1
                continue

            created = self._upsert_candidacy(
                opp, candidate, local_posting, stage_text_by_id, archive_reason_text_by_id
            )
            candidacies_created += int(created)
            candidacies_updated += int(not created)

        # The cap above leaves older opportunities unread on every run. Read
        # client-tagged postings in full: the filter names the posting, so
        # this costs one request per page rather than one per opportunity.
        # Each posting commits with its checkpoint, so an interrupted run
        # keeps its progress and the next run continues from there.
        self.db.commit()
        postings = sorted(self._dtc_postings(), key=_read_order)
        dtc_started = time.monotonic()
        dtc_opportunities_seen = 0
        dtc_postings_read = dtc_postings_failed = dtc_postings_deferred = dtc_postings_current = 0
        consecutive_failures = 0
        for index, posting in enumerate(postings):
            if _is_current(posting, datetime.now(UTC)):
                dtc_postings_current += 1
                continue
            attempted = dtc_postings_read + dtc_postings_failed
            if attempted and (
                time.monotonic() - dtc_started > _DTC_READ_BUDGET_SECONDS
                or consecutive_failures >= _MAX_CONSECUTIVE_POSTING_FAILURES
            ):
                now = datetime.now(UTC)
                dtc_postings_deferred = sum(not _is_current(p, now) for p in postings[index:])
                dtc_postings_current += len(postings) - index - dtc_postings_deferred
                logger.warning(
                    "Lever DTC posting read incomplete: %s of %s postings read",
                    dtc_postings_read, len(postings),
                )
                break
            attempt_at = datetime.now(UTC)
            posting.dtc_last_attempt_at = attempt_at
            self.db.commit()  # survives a crash during this posting, so it cannot block the queue
            new_ids: set[str] = set()
            found = made = matched = linked = updated = 0
            try:
                for opp in self._lever_for_posting(client, posting):
                    if opp.id in seen_ids or opp.id in new_ids:
                        continue
                    new_ids.add(opp.id)
                    found += 1
                    candidate, created = self._resolve_candidate(opp)
                    made += int(created)
                    matched += int(not created)
                    created = self._upsert_candidacy(
                        opp, candidate, posting, stage_text_by_id, archive_reason_text_by_id
                    )
                    linked += int(created)
                    updated += int(not created)
                posting.dtc_last_read_at = datetime.now(UTC)
                self.db.commit()
            except Exception as exc:  # noqa: BLE001 - one posting must not end the run
                self.db.rollback()
                posting.dtc_last_attempt_at = attempt_at
                self.db.commit()
                dtc_postings_failed += 1
                consecutive_failures += 1
                logger.warning("Lever DTC posting read failed: %s", type(exc).__name__)
                continue
            consecutive_failures = 0
            dtc_postings_read += 1
            seen_ids |= new_ids
            dtc_opportunities_seen += found
            candidates_created += made
            candidates_matched += matched
            candidacies_created += linked
            candidacies_updated += updated

        result = {
            "opportunities_seen": len(opportunities),
            "opportunity_limit_reached": limit_reached,
            "dtc_postings_read": dtc_postings_read,
            "dtc_postings_total": len(postings),
            "dtc_postings_current": dtc_postings_current,
            "dtc_postings_failed": dtc_postings_failed,
            "dtc_postings_deferred": dtc_postings_deferred,
            "dtc_postings_remaining": len(unread_postings(postings, datetime.now(UTC))),
            "general_budget_exhausted": general_budget_exhausted,
            "dtc_opportunities_seen": dtc_opportunities_seen,
            "candidates_created": candidates_created,
            "candidates_matched": candidates_matched,
            "candidacies_created": candidacies_created,
            "candidacies_updated": candidacies_updated,
            "skipped_no_local_posting": skipped_no_local_posting,
        }
        logger.info("Lever candidacy sync: %s", result)
        return result

    def _dtc_postings(self) -> list:
        return dtc_postings(self.posting_repo)

    @staticmethod
    def _lever_for_posting(client, posting) -> list:
        return client.list_opportunities(posting_id=posting.lever_posting_id)

    def _upsert_candidacy(
        self, opp, candidate, posting, stage_text_by_id: dict, archive_reason_text_by_id: dict
    ) -> bool:
        """Returns True when a new candidacy was created."""
        canonical_stage = map_lever_stage(stage_text_by_id.get(opp.stage_id, ""))

        if opp.archived and opp.archive_reason_id:
            reason_text = archive_reason_text_by_id.get(opp.archive_reason_id, "")
            status = map_lever_archive_outcome(reason_text)
        else:
            reason_text = None
            status = ApplicationStatus.ACTIVE

        existing = self.candidacy_repo.get_by_lever_opportunity_id(opp.id)
        if existing is None:
            self.candidacy_repo.add(
                RecruitmentCandidacy(
                    recruitment_candidate_id=candidate.id,
                    posting_id=posting.id,
                    lever_opportunity_id=opp.id,
                    current_stage=canonical_stage.value,
                    status=status.value,
                    lever_archive_reason=reason_text,
                )
            )
            return True
        existing.current_stage = canonical_stage.value
        existing.status = status.value
        existing.lever_archive_reason = reason_text
        return False

    def _resolve_candidate(self, opp) -> tuple[RecruitmentCandidate, bool]:
        """Identity is keyed off the stable Lever Contact id — never the
        Opportunity id — so one person with multiple Opportunities maps to
        one ``RecruitmentCandidate``."""
        existing = self.candidate_repo.get_by_lever_contact_id(opp.contact_id)
        now = datetime.now(UTC)
        if existing is not None:
            existing.full_name = opp.name or existing.full_name
            existing.email = opp.email or existing.email
            existing.headline = opp.headline or existing.headline
            existing.tags = json.dumps(list(opp.tags))
            existing.sources = json.dumps(list(opp.sources))
            existing.last_synced_at = now
            return existing, False

        candidate = self.candidate_repo.add(
            RecruitmentCandidate(
                lever_contact_id=opp.contact_id,
                full_name=opp.name or "",
                email=opp.email or "",
                headline=opp.headline or "",
                tags=json.dumps(list(opp.tags)),
                sources=json.dumps(list(opp.sources)),
                last_synced_at=now,
            )
        )
        if self.mapping_repo.find(_PROVIDER, _CONTACT_TYPE, opp.contact_id) is None:
            self.mapping_repo.add(
                ExternalMapping(
                    provider=_PROVIDER,
                    external_object_type=_CONTACT_TYPE,
                    external_id=opp.contact_id,
                    internal_object_type="RecruitmentCandidate",
                    internal_id=candidate.id,
                    last_synced_at=now,
                )
            )
        return candidate, True
