from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integration_event import IntegrationEvent


class IntegrationEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_external_id(self, provider: str, external_event_id: str) -> IntegrationEvent | None:
        return self.db.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.provider == provider,
                IntegrationEvent.external_event_id == external_event_id,
            )
        ).scalars().first()

    def add(self, event: IntegrationEvent) -> IntegrationEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def list_recent(self, limit: int = 50) -> list[IntegrationEvent]:
        return list(
            self.db.execute(
                select(IntegrationEvent).order_by(IntegrationEvent.received_at.desc()).limit(limit)
            ).scalars().all()
        )
