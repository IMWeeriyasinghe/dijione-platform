"""Best-effort audit events to Platform Core (never fails the caller)."""

from __future__ import annotations

import logging

from auth_client_py import PlatformClient

from app.core.config import get_settings

logger = logging.getLogger("onsite-api.platform_audit")


def record(*, actor_id: int | None, action: str, entity_id: int, previous: dict | None, new: dict | None) -> None:
    settings = get_settings()
    try:
        PlatformClient(
            base_url=settings.platform_api_url, internal_secret=settings.internal_service_secret,
            timeout=2.0, caller="onsite-api",
        ).record_audit_event(
            actor_id=actor_id, action=action, entity_type="OnsiteSite", entity_id=entity_id,
            previous_state=previous, new_state=new,
        )
    except Exception:  # noqa: BLE001 - best effort
        logger.debug("audit skipped", exc_info=True)
