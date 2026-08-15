"""Read-only ingestion of Lever Contacts/Opportunities into the local read
model — Candidate (via ExternalMapping) and PostingApplication (Candidate x
Posting candidacy, deliberately NOT the client-owned ``Application``/
``TalentRequest`` tables — see posting_application.py's module docstring).

Same INITIAL / RECONCILIATION READ path as LeverPostingSyncService:

    Lever GET API -> LeverClient -> Provider DTOs -> mapper -> Candidate +
    ExternalMapping + PostingApplication -> DijiTalentFlow read model.

GET-only. Never assigns a client to anything. A candidacy only ever
resolves to a client-visible Application once a separate, explicit,
future step decides to promote a PostingApplication whose Posting has a
VERIFIED PostingClientMapping — not built here.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import ApplicationStatus
from app.integrations.factory import get_lever_client
from app.integrations.lever.mapper import map_lever_archive_outcome, map_lever_stage
from app.models.candidate import Candidate
from app.models.external_mapping import ExternalMapping
from app.models.posting_application import PostingApplication
from app.repositories.integration_repo import ExternalMappingRepository
from app.repositories.posting_application_repo import PostingApplicationRepository
from app.repositories.posting_repo import PostingRepository

logger = logging.getLogger("app.services.lever_contact_application_sync_service")

_PROVIDER = "LEVER"
_CONTACT_TYPE = "contact"
_OPPORTUNITY_TYPE = "opportunity"


class LeverContactApplicationSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.mapping_repo = ExternalMappingRepository(db)
        self.posting_repo = PostingRepository(db)
        self.posting_application_repo = PostingApplicationRepository(db)

    def sync_opportunities(self, limit: int | None = None) -> dict:
        """``limit`` bounds how many Opportunities are pulled in one call —
        this tenant has shown source counts in the hundreds of thousands
        (live discovery), so an unbounded full-tenant pull is never the
        right default for an "initial sync" and must be a deliberate,
        separately-sized decision, not an accidental side effect of
        calling this method."""
        client = get_lever_client()

        # Resolve once — real opportunities carry only stage/archive-reason
        # IDs, not the text mapper.py's functions need.
        stage_text_by_id = {s.id: s.text for s in client.list_stages()}
        archive_reason_text_by_id = {r.id: r.text for r in client.list_archive_reasons()}

        opportunities = client.list_opportunities(limit=limit)

        candidates_created = 0
        candidates_matched = 0
        posting_applications_created = 0
        posting_applications_updated = 0
        skipped_no_local_posting = 0

        for opp in opportunities:
            candidate, created = self._resolve_candidate(opp)
            if created:
                candidates_created += 1
            else:
                candidates_matched += 1

            applications = client.list_applications(opp.id)
            lever_posting_id = applications[0].posting_id if applications else None
            local_posting = (
                self.posting_repo.get_by_lever_id(lever_posting_id)
                if lever_posting_id
                else None
            )
            if local_posting is None:
                # No local Posting to link to yet (posting sync hasn't
                # ingested it, or the opportunity has no application at
                # all). Candidate is still synced above; the candidacy
                # itself is skipped rather than invented against nothing.
                skipped_no_local_posting += 1
                continue

            stage_text = stage_text_by_id.get(opp.stage_id, "")
            canonical_stage = map_lever_stage(stage_text)

            if opp.archived and opp.archive_reason_id:
                reason_text = archive_reason_text_by_id.get(opp.archive_reason_id, "")
                status = map_lever_archive_outcome(reason_text)
            else:
                reason_text = None
                status = ApplicationStatus.ACTIVE

            existing_pa = self.posting_application_repo.get_by_lever_opportunity_id(opp.id)
            if existing_pa is None:
                pa = PostingApplication(
                    candidate_id=candidate.id,
                    posting_id=local_posting.id,
                    lever_opportunity_id=opp.id,
                    current_stage=canonical_stage.value,
                    status=status.value,
                    lever_archive_reason=reason_text,
                )
                self.posting_application_repo.add(pa)
                posting_applications_created += 1
            else:
                existing_pa.current_stage = canonical_stage.value
                existing_pa.status = status.value
                existing_pa.lever_archive_reason = reason_text
                posting_applications_updated += 1

        self.db.flush()
        result = {
            "opportunities_seen": len(opportunities),
            "candidates_created": candidates_created,
            "candidates_matched": candidates_matched,
            "posting_applications_created": posting_applications_created,
            "posting_applications_updated": posting_applications_updated,
            "skipped_no_local_posting": skipped_no_local_posting,
        }
        logger.info("Lever contact/application sync: %s", result)
        return result

    def _resolve_candidate(self, opp) -> tuple[Candidate, bool]:
        """Candidate identity is keyed off the Lever Contact id — never the
        Opportunity id — so one person with multiple Opportunities maps to
        one Candidate (CLAUDE.md §19 Candidate Ownership Rule)."""
        mapping = self.mapping_repo.find(_PROVIDER, _CONTACT_TYPE, opp.contact_id)
        if mapping is not None:
            candidate = self.db.get(Candidate, mapping.internal_id)
            if candidate is not None:
                return candidate, False

        # Fallback: match by email if a mapping doesn't exist yet but a
        # Candidate with this email already does (e.g. seeded/manually
        # created) — avoids creating a duplicate person record.
        existing = None
        if opp.email:
            from app.repositories.candidate_repo import CandidateRepository

            existing = CandidateRepository(self.db).get_by_email(opp.email)

        if existing is not None:
            candidate = existing
            created = False
        else:
            candidate = Candidate(
                full_name=opp.name,
                email=opp.email or f"lever-contact-{opp.contact_id}@unknown.invalid",
                professional_title=opp.headline,
                skills=",".join(opp.tags),
                source="LEVER",
                lever_external_id=opp.contact_id,
            )
            self.db.add(candidate)
            self.db.flush()
            created = True

        self.mapping_repo.add(
            ExternalMapping(
                provider=_PROVIDER,
                external_object_type=_CONTACT_TYPE,
                external_id=opp.contact_id,
                internal_object_type="Candidate",
                internal_id=candidate.id,
                last_synced_at=datetime.now(UTC),
            )
        )
        return candidate, created
