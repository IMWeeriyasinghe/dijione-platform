"""Thin best-effort wrapper over Platform Core's internal notification/audit
surface. Notifications and audit are platform-owned; recruitment-api sends
module_key/role strings (platform-api owns UserModuleRole). Every call here
is best-effort — a Platform Core outage never fails a sync run.
"""

from __future__ import annotations

import logging

from auth_client_py import PlatformClient

from app.core.config import get_settings

logger = logging.getLogger("recruitment-api.platform_notify")


def _client() -> PlatformClient:
    settings = get_settings()
    return PlatformClient(
        base_url=settings.platform_api_url,
        internal_secret=settings.internal_service_secret,
        timeout=2.0,
        caller="recruitment-api",
    )


def notify_user(*, user_id: int, type: str, title: str, body: str = "", related_entity_id: int | None = None) -> None:
    try:
        _client().notify_user(
            user_id=user_id, type=type, title=title, body=body,
            related_entity_type="RecruitmentSyncRun", related_entity_id=related_entity_id,
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.debug("notify_user skipped", exc_info=True)


def notify_module_role(
    *, module_key: str, role: str, type: str, title: str, body: str = "",
    related_entity_id: int | None = None,
) -> None:
    try:
        _client().broadcast_notification(
            module_key=module_key, role=role, type=type, title=title, body=body,
            related_entity_type="RecruitmentSyncRun", related_entity_id=related_entity_id,
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.debug("notify_module_role skipped", exc_info=True)


def record_audit(*, actor_id: int | None, action: str, entity_type: str, entity_id: int, new_state: dict | None = None) -> None:
    try:
        _client().record_audit_event(
            actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id,
            new_state=new_state,
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.debug("record_audit skipped", exc_info=True)
