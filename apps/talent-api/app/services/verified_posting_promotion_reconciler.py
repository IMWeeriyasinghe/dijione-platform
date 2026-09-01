"""VerifiedPostingPromotionReconciler — projects VERIFIED Lever postings
into real DijiTalentFlow operational records.

Recruitment Source (recruitment-api) supplies posting + candidacy facts.
``PostingClientMappingReconciler`` already resolves the fail-closed
posting -> client trust decision (VERIFIED / UNMAPPED / ...). This
reconciler consumes ONLY the VERIFIED subset and projects it:

    VERIFIED PostingClientMapping  -> exactly one TalentRequest
    Lever person (candidate_external_id) -> exactly one Candidate master
    Lever candidacy (opportunity)  -> exactly one Application

Idempotent, like its sibling: get-or-create by a stable external key,
diff-then-write, no commit (the caller commits). Fail closed, always:
  * only a VERIFIED mapping with a local posting projection promotes;
  * UNMAPPED / REJECTED / any non-VERIFIED status promotes nothing;
  * a VERIFIED-but-archived posting with no existing TalentRequest never
    gets a *new* one (an existing one keeps receiving source-fact refresh);
  * a candidacy against a posting with no VERIFIED TalentRequest is
    skipped entirely — no Candidate is created for it either.

Source vs workflow, strictly separated (never blur the two):
  * refreshed every run: TalentRequest.designation/location;
    Candidate.full_name/professional_title/email (only when non-blank);
    Application.current_stage/lever_archive_reason;
  * set once at creation, then TalentFlow-owned forever: TalentRequest
    workflow fields (current_stage/lifecycle_status/customer_success_status/
    ta_status/client_safe_status_text/priority/description/notes);
    Candidate.availability_status/summary/skills/cv_reference/phone/location;
    Application.status/score/recruiter_notes/client_visible_notes/
    rejection_reason/is_client_visible (always False on promotion — a TA
    must explicitly curate client visibility; see CandidateService and
    TalentRequestService for the exact field-by-field split).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.constants import CANONICAL_STAGE_ORDER, ApplicationStatus, CanonicalStage
from app.models.application import Application
from app.repositories.application_repo import ApplicationRepository
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.repositories.posting_repo import PostingRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.services.audit_service import AuditService
from app.services.candidate_service import CandidateService
from app.services.talent_request_service import TalentRequestService

logger = logging.getLogger("talent-api.promotion_reconciler")

_CANDIDACY_PAGE_LIMIT = 500
_STAGE_RANK = {s.value: i for i, s in enumerate(CANONICAL_STAGE_ORDER)}
_VALID_STATUSES = {s.value for s in ApplicationStatus}
_DEFAULT_STAGE = CanonicalStage.SOURCING.value
_DEFAULT_STATUS = ApplicationStatus.ACTIVE.value


@dataclass
class PromotionSummary:
    verified_postings: int = 0
    talent_requests_created: int = 0
    talent_requests_updated: int = 0
    candidates_created: int = 0
    candidates_updated: int = 0
    applications_created: int = 0
    applications_updated: int = 0
    candidacies_seen: int = 0
    candidacies_skipped_no_verified_request: int = 0
    collapsed_duplicate_candidacies: int = 0
    candidacies_available: bool = True
    unchanged: int = 0
    transitions: list[str] = field(default_factory=list)


def _stage_rank(stage: str) -> int:
    return _STAGE_RANK.get(stage, -1)


def _safe_stage(stage: str | None) -> str:
    return stage if stage in _STAGE_RANK else _DEFAULT_STAGE


def _safe_status(status: str | None) -> str:
    return status if status in _VALID_STATUSES else _DEFAULT_STATUS


def _pick_candidacy(rows: list[dict]) -> dict:
    """Deterministic choice when more than one Lever opportunity exists for
    the same (person, posting) pair: the most-advanced canonical stage,
    then the most recently synced, then the largest external id — never
    arbitrary dict/list order, so a re-run always converges on the same
    row."""
    return max(
        rows,
        key=lambda r: (
            _stage_rank(r.get("current_stage") or ""),
            r.get("synced_at") or "",
            r.get("external_id") or "",
        ),
    )


class VerifiedPostingPromotionReconciler:
    def __init__(self, db: Session):
        self.db = db
        self.mappings = PostingClientMappingRepository(db)
        self.postings = PostingRepository(db)
        self.requests = TalentRequestService(db)
        self.request_repo = TalentRequestRepository(db)
        self.candidates = CandidateService(db)
        self.applications = ApplicationRepository(db)
        self.audit = AuditService()

    def reconcile(self, *, candidacies: list[dict] | None) -> PromotionSummary:
        summary = PromotionSummary()
        tr_by_posting: dict[str, object] = {}

        for mapping in self.mappings.list_verified():
            ref = self.postings.get_ref_by_external_id(mapping.posting_external_id)
            if ref is None:
                summary.transitions.append(
                    f"{mapping.posting_external_id}:no_projection_skipped"
                )
                continue

            existing_tr = self.request_repo.get_by_posting_external_id(mapping.posting_external_id)
            if existing_tr is None:
                if ref.archived:
                    summary.transitions.append(
                        f"{mapping.posting_external_id}:archived_no_new_tr"
                    )
                    continue
                tr = self.requests.create_from_posting(
                    client_id=mapping.client_id,
                    posting_external_id=mapping.posting_external_id,
                    designation=ref.title,
                    location=ref.location,
                )
                summary.talent_requests_created += 1
            else:
                tr = existing_tr
                if self.requests.reconcile_posting_facts(
                    tr, designation=ref.title, location=ref.location
                ):
                    summary.talent_requests_updated += 1
                else:
                    summary.unchanged += 1

            summary.verified_postings += 1
            tr_by_posting[mapping.posting_external_id] = tr

        self.db.flush()

        if candidacies is None:
            summary.candidacies_available = False
            return summary

        summary.candidacies_seen = len(candidacies)
        if len(candidacies) >= _CANDIDACY_PAGE_LIMIT:
            summary.transitions.append("candidacy_page_limit_hit")

        groups: dict[tuple[str, str], list[dict]] = {}
        for row in candidacies:
            key = (row.get("candidate_external_id") or "", row.get("posting_external_id") or "")
            groups.setdefault(key, []).append(row)

        for (candidate_ext, posting_ext), rows in groups.items():
            tr = tr_by_posting.get(posting_ext)
            if tr is None:
                summary.candidacies_skipped_no_verified_request += len(rows)
                continue

            chosen = _pick_candidacy(rows)
            if len(rows) > 1:
                summary.collapsed_duplicate_candidacies += len(rows) - 1
                summary.transitions.append(
                    f"collapsed_{len(rows)}_to_1:{chosen.get('external_id')}"
                )

            candidate, cstate = self.candidates.upsert_from_source(
                lever_external_id=candidate_ext,
                full_name=chosen.get("candidate_name") or "",
                email=chosen.get("candidate_email") or "",
                headline=chosen.get("candidate_headline") or "",
            )
            if cstate == "created":
                summary.candidates_created += 1
            elif cstate == "updated":
                summary.candidates_updated += 1
            else:
                summary.unchanged += 1

            self._reconcile_application(candidate.id, tr.id, chosen, summary)

        self.db.flush()
        return summary

    def _reconcile_application(
        self, candidate_id: int, talent_request_id: int, chosen: dict, summary: PromotionSummary
    ) -> None:
        src_stage = _safe_stage(chosen.get("current_stage"))
        src_reason = chosen.get("lever_archive_reason")
        opportunity_id = chosen.get("external_id") or ""

        existing = self.applications.get_for_pair(candidate_id, talent_request_id)
        if existing is None:
            application = Application(
                candidate_id=candidate_id,
                talent_request_id=talent_request_id,
                current_stage=src_stage,
                status=_safe_status(chosen.get("status")),
                lever_opportunity_id=opportunity_id or None,
                lever_archive_reason=src_reason,
                is_client_visible=False,
            )
            self.applications.add(application)
            summary.applications_created += 1
            self._audit_application(application, "system_promoted", {
                "candidate_id": candidate_id, "talent_request_id": talent_request_id,
                "lever_opportunity_id": opportunity_id,
            })
            return

        changed = False
        if existing.current_stage != src_stage:
            existing.current_stage = src_stage
            changed = True
        if existing.lever_archive_reason != src_reason:
            existing.lever_archive_reason = src_reason
            changed = True
        if existing.lever_opportunity_id is None and opportunity_id:
            existing.lever_opportunity_id = opportunity_id
            changed = True
        elif opportunity_id and existing.lever_opportunity_id != opportunity_id:
            # A different opportunity id now maps to the same (candidate,
            # request) pair (e.g. Lever re-opened a fresh opportunity for
            # the same person/posting). Keep the stable, already-persisted
            # id rather than reassigning it — reassigning could collide
            # with the partial-unique index on another row and is not
            # worth the churn for a diagnostic-only field.
            summary.transitions.append(
                f"opportunity_id_stable_kept:{existing.lever_opportunity_id}"
            )

        if changed:
            summary.applications_updated += 1
            self._audit_application(existing, "source_facts_refreshed", {
                "current_stage": existing.current_stage,
                "lever_archive_reason": existing.lever_archive_reason,
            })
        else:
            summary.unchanged += 1

    def _audit_application(self, application: Application, action: str, meta: dict) -> None:
        try:
            self.audit.log(
                actor_id=None,
                action=f"application.{action}",
                entity_type="Application",
                entity_id=application.id,
                new_state=meta,
            )
        except Exception:  # noqa: BLE001 - best-effort, mirrors PostingClientMappingReconciler
            logger.debug("promotion reconcile audit skipped", exc_info=True)
