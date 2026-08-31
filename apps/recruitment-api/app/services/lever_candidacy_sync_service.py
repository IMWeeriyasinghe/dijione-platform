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
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import ApplicationStatus
from app.integrations.factory import get_lever_client
from app.integrations.lever.mapper import map_lever_archive_outcome, map_lever_stage
from app.models.external_mapping import ExternalMapping
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.models.recruitment_candidate import RecruitmentCandidate
from app.repositories.candidacy_repo import (
    RecruitmentCandidacyRepository,
    RecruitmentCandidateRepository,
)
from app.repositories.integration_repo import ExternalMappingRepository
from app.repositories.posting_repo import PostingRepository

logger = logging.getLogger("recruitment-api.lever_candidacy_sync_service")

_PROVIDER = "LEVER"
_CONTACT_TYPE = "contact"


class LeverCandidacySyncService:
    def __init__(self, db: Session):
        self.db = db
        self.mapping_repo = ExternalMappingRepository(db)
        self.posting_repo = PostingRepository(db)
        self.candidate_repo = RecruitmentCandidateRepository(db)
        self.candidacy_repo = RecruitmentCandidacyRepository(db)

    def sync_opportunities(self, limit: int | None = None) -> dict:
        client = get_lever_client()

        stage_text_by_id = {s.id: s.text for s in client.list_stages()}
        archive_reason_text_by_id = {r.id: r.text for r in client.list_archive_reasons()}

        opportunities = client.list_opportunities(limit=limit)

        candidates_created = 0
        candidates_matched = 0
        candidacies_created = 0
        candidacies_updated = 0
        skipped_no_local_posting = 0

        for opp in opportunities:
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

            stage_text = stage_text_by_id.get(opp.stage_id, "")
            canonical_stage = map_lever_stage(stage_text)

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
                        posting_id=local_posting.id,
                        lever_opportunity_id=opp.id,
                        current_stage=canonical_stage.value,
                        status=status.value,
                        lever_archive_reason=reason_text,
                    )
                )
                candidacies_created += 1
            else:
                existing.current_stage = canonical_stage.value
                existing.status = status.value
                existing.lever_archive_reason = reason_text
                candidacies_updated += 1

        self.db.flush()
        result = {
            "opportunities_seen": len(opportunities),
            "candidates_created": candidates_created,
            "candidates_matched": candidates_matched,
            "candidacies_created": candidacies_created,
            "candidacies_updated": candidacies_updated,
            "skipped_no_local_posting": skipped_no_local_posting,
        }
        logger.info("Lever candidacy sync: %s", result)
        return result

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
