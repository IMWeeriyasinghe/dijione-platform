"""Processes inbound HubSpot webhook events idempotently (CLAUDE.md
§63-65). No HubSpot event currently drives a mutation anywhere in
DijiOne — HubSpot doesn't own recruitment pipeline state, and no other
domain reads commercial facts yet — so this exists to prove the
architecture and log activity for future use.
"""

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import ProcessingStatus
from app.models.integration_event import IntegrationEvent
from app.repositories.integration_repo import IntegrationEventRepository

_PROVIDER = "HUBSPOT"


class SyncService:
    def __init__(self, db: Session):
        self.db = db
        self.event_repo = IntegrationEventRepository(db)

    def process_hubspot_event(self, payload: dict) -> IntegrationEvent:
        external_event_id = str(payload.get("eventId") or payload.get("id", ""))
        event_type = str(payload.get("subscriptionType", payload.get("event", "unknown")))
        existing = self.event_repo.find_by_external_id(_PROVIDER, external_event_id)
        if existing is not None:
            existing.processing_status = ProcessingStatus.IGNORED_DUPLICATE.value
            return existing

        event = IntegrationEvent(
            provider=_PROVIDER,
            external_event_id=external_event_id,
            event_type=event_type,
            processing_status=ProcessingStatus.PROCESSED.value,
            payload_reference=json.dumps(payload, default=str)[:4000],
            processed_at=datetime.now(UTC),
        )
        self.event_repo.add(event)
        return event
