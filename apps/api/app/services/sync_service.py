import json

from sqlalchemy.orm import Session

from app.core.constants import IntegrationProvider, NotificationType, ProcessingStatus
from app.integrations.lever.mapper import map_lever_stage
from app.models.integration_event import IntegrationEvent
from app.repositories.application_repo import ApplicationRepository
from app.repositories.integration_repo import ExternalMappingRepository, IntegrationEventRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


class SyncService:
    """Processes inbound webhook events idempotently (CLAUDE.md §63-65).

    A duplicate delivery of the same (provider, external_event_id) is
    recorded but not reprocessed — this is what keeps repeated webhook
    deliveries from duplicating domain records.
    """

    def __init__(self, db: Session):
        self.db = db
        self.event_repo = IntegrationEventRepository(db)
        self.mapping_repo = ExternalMappingRepository(db)
        self.application_repo = ApplicationRepository(db)
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    def process_lever_event(self, payload: dict) -> IntegrationEvent:
        external_event_id = str(payload.get("triggerEvent", {}).get("id") or payload.get("id", ""))
        event_type = str(payload.get("event", "unknown"))
        existing = self.event_repo.find_by_external_id(IntegrationProvider.LEVER.value, external_event_id)
        if existing is not None:
            return existing

        event = IntegrationEvent(
            provider=IntegrationProvider.LEVER.value,
            external_event_id=external_event_id,
            event_type=event_type,
            processing_status=ProcessingStatus.RECEIVED.value,
            payload_reference=json.dumps(payload, default=str)[:4000],
        )
        self.event_repo.add(event)

        try:
            self._apply_lever_event(payload, event_type)
            event.processing_status = ProcessingStatus.PROCESSED.value
        except Exception as exc:  # noqa: BLE001 — record and continue
            event.processing_status = ProcessingStatus.FAILED.value
            event.error = str(exc)[:1000]
            self.notifications.notify_module_role(
                module_key="talent-flow",
                role="TA_MANAGER",
                type=NotificationType.INTEGRATION_SYNC_FAILED.value,
                title="Lever sync failed",
                body=str(exc)[:200],
            )
        from datetime import UTC, datetime

        event.processed_at = datetime.now(UTC)
        return event

    def _apply_lever_event(self, payload: dict, event_type: str) -> None:
        opportunity_id = payload.get("opportunityId") or payload.get("data", {}).get("opportunityId")
        stage_text = payload.get("stage") or payload.get("data", {}).get("stage")
        if not opportunity_id or not stage_text:
            return

        mapping = self.mapping_repo.find("LEVER", "opportunity", str(opportunity_id))
        if mapping is None:
            return  # opportunity not linked to an internal application yet

        application = self.application_repo.get_by_id(mapping.internal_id)
        if application is None:
            return

        canonical_stage = map_lever_stage(str(stage_text))
        previous_stage = application.current_stage
        application.current_stage = canonical_stage.value
        self.audit.log(
            actor_id=None,
            action="application.stage_synced_from_lever",
            entity_type="Application",
            entity_id=application.id,
            previous_state={"current_stage": previous_stage},
            new_state={"current_stage": canonical_stage.value, "lever_stage_text": stage_text},
        )

    def process_hubspot_event(self, payload: dict) -> IntegrationEvent:
        external_event_id = str(payload.get("eventId") or payload.get("id", ""))
        event_type = str(payload.get("subscriptionType", payload.get("event", "unknown")))
        existing = self.event_repo.find_by_external_id(
            IntegrationProvider.HUBSPOT.value, external_event_id
        )
        if existing is not None:
            return existing

        from datetime import UTC, datetime

        event = IntegrationEvent(
            provider=IntegrationProvider.HUBSPOT.value,
            external_event_id=external_event_id,
            event_type=event_type,
            processing_status=ProcessingStatus.PROCESSED.value,
            payload_reference=json.dumps(payload, default=str)[:4000],
            processed_at=datetime.now(UTC),
        )
        self.event_repo.add(event)
        return event
