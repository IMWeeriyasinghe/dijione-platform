"""Notification is platform-owned — talent-api creates notifications
through Platform Core's internal API instead of writing to a local table.
Same ``.notify_user(...)``/``.notify_module_role(...)`` shape as the
pre-split service so call sites elsewhere didn't need to change.

Best-effort: a Platform Core outage must not fail a talent request/message
action (CR §21, §27).
"""

from __future__ import annotations

from auth_client_py import PlatformClient

from app.core.config import get_settings


class NotificationService:
    def __init__(self, client: PlatformClient | None = None):
        settings = get_settings()
        self.client = client or PlatformClient(
            base_url=settings.platform_api_url, internal_secret=settings.internal_service_secret,
            timeout=2.0, caller="talent-api",
        )

    def notify_user(
        self,
        *,
        user_id: int,
        type: str,
        title: str,
        body: str = "",
        related_entity_type: str | None = None,
        related_entity_id: int | None = None,
    ) -> None:
        self.client.notify_user(
            user_id=user_id, type=type, title=title, body=body,
            related_entity_type=related_entity_type, related_entity_id=related_entity_id,
        )

    def notify_module_role(
        self,
        *,
        module_key: str,
        role: str,
        type: str,
        title: str,
        body: str = "",
        related_entity_type: str | None = None,
        related_entity_id: int | None = None,
        client_id: int | None = None,
    ) -> None:
        self.client.broadcast_notification(
            module_key=module_key, role=role, type=type, title=title, body=body,
            related_entity_type=related_entity_type, related_entity_id=related_entity_id,
            client_id=client_id,
        )
