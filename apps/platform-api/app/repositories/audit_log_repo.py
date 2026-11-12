from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, entry: AuditLog) -> AuditLog:
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_by_event_id(self, event_id: str) -> AuditLog | None:
        return self.db.execute(select(AuditLog).where(AuditLog.event_id == event_id)).scalars().first()

    def list_for_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())
