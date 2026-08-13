import json

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_log_repo import AuditLogRepository


class AuditService:
    def __init__(self, db: Session):
        self.repo = AuditLogRepository(db)

    def log(
        self,
        *,
        actor_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int,
        previous_state: dict | str | None = None,
        new_state: dict | str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        def _serialize(value: dict | str | None) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            return json.dumps(value, default=str)

        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_state=_serialize(previous_state),
            new_state=_serialize(new_state),
            event_metadata=_serialize(metadata),
        )
        return self.repo.add(entry)
