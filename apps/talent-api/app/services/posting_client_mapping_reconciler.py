"""PostingClientMappingReconciler — TalentFlow trust decision.

Consumes the governed DTC posting tag (a Recruitment Source provider fact,
parsed by app/recruitment_source/dtc.py) and reconciles the DijiOne-owned
``PostingClientMapping`` trust record. Runs inside the Recruitment Source
sync (scheduled + ad-hoc). Idempotent.

Fail closed, always:
  * only a single well-formed DTC tag that exactly matches exactly one
    Client sets VERIFIED (source=LEVER_DTC_TAG);
  * unknown / malformed / multiple / ambiguous  -> never client-visible;
  * a human MANUAL VERIFIED mapping is NEVER overwritten by a tag change —
    a conflict is flagged for review;
  * a removed/broken DTC tag on a previously DTC-resolved mapping reverts it
    to UNMAPPED (visibility lost);
  * a Client row is NEVER auto-created from a tag.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import (
    MODULE_TALENT_FLOW,
    DtcResolutionStatus,
    NotificationType,
    PostingClientMappingSource,
    PostingClientMappingStatus,
    TalentFlowRole,
)
from app.models.posting_client_mapping import PostingClientMapping
from app.recruitment_source.dtc import DtcParseStatus, parse_dtc
from app.repositories.client_repo import ClientRepository
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

logger = logging.getLogger("talent-api.dtc_reconciler")

_VERIFIED = PostingClientMappingStatus.VERIFIED.value
_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value
_REJECTED = PostingClientMappingStatus.REJECTED.value
_MANUAL = PostingClientMappingSource.MANUAL.value
_DTC = PostingClientMappingSource.LEVER_DTC_TAG.value


@dataclass
class ReconcileSummary:
    resolved: int = 0
    reassigned: int = 0
    reverted: int = 0
    unknown: int = 0
    ambiguous: int = 0
    malformed: int = 0
    no_tag: int = 0
    conflicts: int = 0
    unchanged: int = 0
    transitions: list[str] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return self.resolved + self.reassigned + self.reverted + self.conflicts


class PostingClientMappingReconciler:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PostingClientMappingRepository(db)
        self.clients = ClientRepository(db)
        self.audit = AuditService()
        self.notifications = NotificationService()

    def reconcile_all(self) -> ReconcileSummary:
        summary = ReconcileSummary()
        for mapping in self.repo.list_all_with_posting():
            posting = mapping.posting
            if posting is None:
                continue
            self._reconcile_one(mapping, self._tags(posting), summary)
        self.db.flush()
        return summary

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _tags(posting) -> list[str]:
        if not posting.tags:
            return []
        try:
            v = json.loads(posting.tags)
            return [t for t in v if isinstance(t, str)] if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []

    def _reconcile_one(
        self, m: PostingClientMapping, tags: list[str], s: ReconcileSummary
    ) -> None:
        now = datetime.now(UTC)
        m.last_reconciled_at = now
        parsed = parse_dtc(tags)

        # A human REJECTED decision is absolute — DTC never un-rejects it.
        if m.status == _REJECTED:
            m.dtc_source_tag = parsed.raw_tag if parsed.status is DtcParseStatus.OK else None
            s.unchanged += 1
            return

        manual_verified = m.status == _VERIFIED and m.source == _MANUAL
        dtc_verified = m.status == _VERIFIED and m.source == _DTC

        if parsed.status is DtcParseStatus.NO_TAG:
            m.dtc_source_tag = None
            if dtc_verified:
                self._revert(m, DtcResolutionStatus.NO_DTC_TAG, "revoked_dtc_removed", s)
            elif manual_verified:
                m.resolution_status = DtcResolutionStatus.RESOLVED.value
                s.unchanged += 1
            else:
                m.resolution_status = DtcResolutionStatus.NO_DTC_TAG.value
                s.no_tag += 1
            return

        if parsed.status is DtcParseStatus.MALFORMED:
            m.dtc_source_tag = parsed.raw_tag
            if dtc_verified:
                self._revert(m, DtcResolutionStatus.MALFORMED_TAG, "revoked_dtc_malformed", s)
            else:
                m.resolution_status = DtcResolutionStatus.MALFORMED_TAG.value
                s.malformed += 1
            return

        if parsed.status is DtcParseStatus.MULTIPLE:
            m.dtc_source_tag = " | ".join(parsed.raw_tags)[:255]
            if dtc_verified:
                self._revert(m, DtcResolutionStatus.AMBIGUOUS_MULTIPLE_TAGS, "revoked_dtc_ambiguous", s)
            else:
                m.resolution_status = DtcResolutionStatus.AMBIGUOUS_MULTIPLE_TAGS.value
                s.ambiguous += 1
            return

        # parsed.status is OK
        m.dtc_source_tag = parsed.raw_tag
        matches = self.clients.find_by_name(parsed.client_name or "")

        if len(matches) == 0:
            if dtc_verified:
                self._revert(m, DtcResolutionStatus.UNKNOWN_CLIENT_IDENTIFIER, "revoked_dtc_unknown", s)
            else:
                if not manual_verified:
                    m.status = _UNMAPPED
                    m.client_id = None
                m.resolution_status = DtcResolutionStatus.UNKNOWN_CLIENT_IDENTIFIER.value
                s.unknown += 1
            return

        if len(matches) > 1:
            if dtc_verified:
                self._revert(m, DtcResolutionStatus.AMBIGUOUS_CLIENT_NAME, "revoked_dtc_ambiguous", s)
            else:
                m.resolution_status = DtcResolutionStatus.AMBIGUOUS_CLIENT_NAME.value
                s.ambiguous += 1
            return

        target = matches[0]

        if manual_verified:
            if m.client_id == target.id:
                m.resolution_status = DtcResolutionStatus.RESOLVED.value  # manual agrees
                s.unchanged += 1
            else:
                m.resolution_status = DtcResolutionStatus.CONFLICT_MANUAL_OVERRIDE.value
                s.conflicts += 1
                self._audit(m, "dtc_conflict_manual_override", {
                    "manual_client_id": m.client_id, "dtc_tag": parsed.raw_tag,
                    "dtc_client_id": target.id,
                })
                self._notify_conflict(m, target.name)
            return

        # No conflicting human decision — set/repoint VERIFIED via DTC.
        if m.status == _VERIFIED and m.source == _DTC and m.client_id == target.id:
            m.resolution_status = DtcResolutionStatus.RESOLVED.value
            s.unchanged += 1
            return

        was_reassign = m.status == _VERIFIED and m.source == _DTC and m.client_id != target.id
        prev = {"status": m.status, "client_id": m.client_id, "source": m.source}
        m.status = _VERIFIED
        m.client_id = target.id
        m.source = _DTC
        m.verified_by_user_id = None  # system-resolved from the governed tag
        m.verified_at = now
        m.resolution_status = DtcResolutionStatus.RESOLVED.value
        if was_reassign:
            s.reassigned += 1
            s.transitions.append(f"{m.posting_id}:reassigned_dtc_changed")
            self._audit(m, "dtc_reassigned", {"previous": prev, "dtc_tag": parsed.raw_tag,
                                              "client_id": target.id})
        else:
            s.resolved += 1
            s.transitions.append(f"{m.posting_id}:resolved_from_dtc")
            self._audit(m, "dtc_resolved", {"previous": prev, "dtc_tag": parsed.raw_tag,
                                            "client_id": target.id})

    def _revert(
        self, m: PostingClientMapping, reason: DtcResolutionStatus, tag: str, s: ReconcileSummary
    ) -> None:
        prev = {"status": m.status, "client_id": m.client_id, "source": m.source}
        m.status = _UNMAPPED
        m.client_id = None
        m.source = ""
        m.verified_by_user_id = None
        m.verified_at = None
        m.resolution_status = reason.value
        s.reverted += 1
        s.transitions.append(f"{m.posting_id}:{tag}")
        self._audit(m, tag, {"previous": prev, "reason": reason.value})

    def _audit(self, m: PostingClientMapping, action: str, meta: dict) -> None:
        try:
            self.audit.log(
                actor_id=None,
                action=f"posting.client_mapping.{action}",
                entity_type="PostingClientMapping",
                entity_id=m.id,
                new_state=meta,
            )
        except Exception:  # noqa: BLE001 - best-effort
            logger.debug("dtc reconcile audit skipped", exc_info=True)

    def _notify_conflict(self, m: PostingClientMapping, dtc_client_name: str) -> None:
        try:
            self.notifications.notify_module_role(
                module_key=MODULE_TALENT_FLOW,
                role=TalentFlowRole.TA_MANAGER.value,
                type=NotificationType.INTEGRATION_SYNC_FAILED.value,
                title="Recruitment posting mapping needs review",
                body=(
                    f"A posting is manually mapped to a different client than its Lever "
                    f"tag ('{m.dtc_source_tag}' → {dtc_client_name}). The manual mapping "
                    f"was kept — re-verify it or correct the Lever tag."
                ),
                related_entity_type="PostingClientMapping",
                related_entity_id=m.id,
            )
        except Exception:  # noqa: BLE001 - best-effort
            logger.debug("dtc conflict notification skipped", exc_info=True)
