import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_log_repo import AuditLogRepository


class AuditEventConflict(Exception):
    """An event_id was reused for different event content."""


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

    def log_once(self, *, event_id: str, **fields) -> bool:
        """Record an event exactly once. True if this call recorded it, False if
        an identical event is already recorded. The unique constraint decides,
        so concurrent deliveries cannot both insert."""
        try:
            with self.repo.db.begin_nested():
                entry = self.log(**fields)
                entry.event_id = event_id
                self.repo.db.flush()
            return True
        except IntegrityError:
            existing = self.repo.get_by_event_id(event_id)
            if existing is None:
                raise  # another constraint, such as an unknown actor
        if not _same_content(existing, entry):
            raise AuditEventConflict
        return False


def _same_content(a: AuditLog, b: AuditLog) -> bool:
    fields = ("actor_id", "action", "entity_type", "entity_id", "previous_state", "new_state", "event_metadata")
    return all(getattr(a, f) == getattr(b, f) for f in fields)
