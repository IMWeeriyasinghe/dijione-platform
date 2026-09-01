from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.external_mapping import ExternalMapping
from app.models.integration_event import IntegrationEvent


class ExternalMappingRepository:
    def __init__(self, db: Session):
        self.db = db

    def find(
        self, provider: str, external_object_type: str, external_id: str
    ) -> ExternalMapping | None:
        stmt = select(ExternalMapping).where(
            ExternalMapping.provider == provider,
            ExternalMapping.external_object_type == external_object_type,
            ExternalMapping.external_id == external_id,
        )
        return self.db.execute(stmt).scalars().first()

    def add(self, mapping: ExternalMapping) -> ExternalMapping:
        self.db.add(mapping)
        self.db.flush()
        return mapping


class IntegrationEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_external_id(self, provider: str, external_event_id: str) -> IntegrationEvent | None:
        stmt = select(IntegrationEvent).where(
            IntegrationEvent.provider == provider,
            IntegrationEvent.external_event_id == external_event_id,
        )
        return self.db.execute(stmt).scalars().first()

    def add(self, event: IntegrationEvent) -> IntegrationEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def list_recent(self, limit: int = 50) -> list[IntegrationEvent]:
        stmt = select(IntegrationEvent).order_by(IntegrationEvent.received_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())
