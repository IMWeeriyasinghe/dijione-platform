"""AuditLog is platform-owned — talent-api records audit events through
Platform Core's internal API instead of writing to a local table. Same
``.log(...)`` shape as the pre-split service so call sites elsewhere in this
codebase didn't need to change, only how the write actually happens.

Best-effort: a Platform Core outage must not fail a talent request/
application/interview/document action (CR §21, §27).
"""

from __future__ import annotations

from auth_client_py import PlatformClient

from app.core.config import get_settings


class AuditService:
    def __init__(self, client: PlatformClient | None = None):
        settings = get_settings()
        self.client = client or PlatformClient(
            base_url=settings.platform_api_url, internal_secret=settings.internal_service_secret,
            timeout=2.0, caller="talent-api",
        )

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
    ) -> None:
        self.client.record_audit_event(
            actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id,
            previous_state=previous_state, new_state=new_state, metadata=metadata,
        )
