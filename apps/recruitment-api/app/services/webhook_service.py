"""Idempotent processing of inbound Lever webhook deliveries
(CLAUDE.md §63-65). A duplicate (provider, external_event_id) delivery is
recorded but not reprocessed. A stage-change event updates the local
``RecruitmentCandidacy`` read model — never any DijiTalentFlow table.
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import NotificationType, ProcessingStatus
from app.integrations.lever.mapper import map_lever_stage
from app.models.integration_event import IntegrationEvent
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.repositories.integration_repo import IntegrationEventRepository
from app.services import platform_notify

logger = logging.getLogger("recruitment-api.webhook_service")

_PROVIDER = "LEVER"


class WebhookService:
    def __init__(self, db: Session):
        self.db = db
        self.event_repo = IntegrationEventRepository(db)

    def process_lever_event(self, payload: dict) -> IntegrationEvent:
        external_event_id = str(
            payload.get("triggerEvent", {}).get("id") or payload.get("id", "")
        )
        event_type = str(payload.get("event", "unknown"))

        existing = self.event_repo.find_by_external_id(_PROVIDER, external_event_id)
        if existing is not None:
            existing.processing_status = ProcessingStatus.IGNORED_DUPLICATE.value
            return existing

        event = IntegrationEvent(
            provider=_PROVIDER,
            external_event_id=external_event_id,
            event_type=event_type,
            processing_status=ProcessingStatus.RECEIVED.value,
            payload_reference=json.dumps(payload, default=str)[:4000],
        )
        self.event_repo.add(event)

        try:
            self._apply(payload)
            event.processing_status = ProcessingStatus.PROCESSED.value
        except Exception as exc:  # noqa: BLE001 - record and continue
            event.processing_status = ProcessingStatus.FAILED.value
            event.error = str(exc)[:1000]
            platform_notify.notify_module_role(
                module_key="talent-flow",
                role="TA_MANAGER",
                type=NotificationType.INTEGRATION_SYNC_FAILED.value,
                title="Lever webhook processing failed",
                body=str(exc)[:200],
            )
        event.processed_at = datetime.now(UTC)
        return event

    def _apply(self, payload: dict) -> None:
        data = payload.get("data", {})
        opportunity_id = payload.get("opportunityId") or data.get("opportunityId")
        stage_text = payload.get("stage") or data.get("stage")
        if not opportunity_id or not stage_text:
            return
        candidacy = self.db.execute(
            select(RecruitmentCandidacy).where(
                RecruitmentCandidacy.lever_opportunity_id == str(opportunity_id)
            )
        ).scalars().first()
        if candidacy is None:
            return  # not ingested yet — the next full sync will pick it up
        candidacy.current_stage = map_lever_stage(str(stage_text)).value
