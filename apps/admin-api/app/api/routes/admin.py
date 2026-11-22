"""DijiOne Admin Center API — public contract unchanged from the pre-split
``apps/api``'s ``/api/admin/*`` (admin-web calls these exact paths/shapes).

Internally this is now a thin orchestrator: identity/role/module-registry/
audit mutations forward to Platform Core with the caller's own bearer token
(``platform_gateway``). Client names now come from Platform Core itself
(it owns canonical Client identity — Architecture Completion Plan §6.1);
the only talent-api call left is the dashboard's live pending-request
count, best-effort so a TalentFlow outage never breaks administration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import get_bearer_token
from app.services.platform_gateway import (
    PlatformClient,
    call_platform_admin,
    forward_platform_admin,
    get_platform_client,
)
from app.services.talent_gateway import (
    get_talent_client,
    pending_talent_requests_within_budget,
    start_pending_talent_requests,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/dashboard")
def get_dashboard(
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    # Both reads start together; Platform Core still authorizes the caller, and its
    # refusal (401/403) is returned without the talent figure ever reaching the caller.
    pending = start_pending_talent_requests(talent)
    dashboard = call_platform_admin(platform, "GET", "/api/platform/admin/dashboard", bearer_token=bearer_token)
    dashboard["pending_talent_requests"] = pending_talent_requests_within_budget(pending)
    return dashboard


@router.get("/users")
def list_users(
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    return call_platform_admin(platform, "GET", "/api/platform/admin/users", bearer_token=bearer_token)


@router.post("/users", status_code=201)
def create_user(
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(platform, "POST", "/api/platform/admin/users", bearer_token=bearer_token, json=payload)


@router.get("/directory/users")
def search_directory(
    q: str = Query(min_length=2, max_length=64),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    return call_platform_admin(
        platform, "GET", "/api/platform/admin/directory/users", bearer_token=bearer_token, params={"q": q}
    )


@router.get("/directory/users/{object_id}/photo")
def directory_photo(
    object_id: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(
        platform, "GET", f"/api/platform/admin/directory/users/{object_id}/photo", bearer_token=bearer_token
    )


@router.post("/users/from-directory", status_code=201)
def add_from_directory(
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    """201 with the new profile, or 409 with ``existing_user_id`` (passed through unchanged)."""
    return forward_platform_admin(
        platform, "POST", "/api/platform/admin/users/from-directory", bearer_token=bearer_token, json=payload
    )


@router.post("/users/{user_id}/verify-directory")
def verify_directory(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "POST", f"/api/platform/admin/users/{user_id}/verify-directory", bearer_token=bearer_token
    )


@router.post("/employee-records/reconcile")
def reconcile_employee_records(
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "POST", "/api/platform/admin/employee-records/reconcile", bearer_token=bearer_token
    )


@router.get("/users/{user_id}/photo")
def user_photo(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(platform, "GET", f"/api/platform/admin/users/{user_id}/photo", bearer_token=bearer_token)


@router.get("/users/{user_id}/entra-groups")
def user_entra_groups(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    return call_platform_admin(
        platform, "GET", f"/api/platform/admin/users/{user_id}/entra-groups", bearer_token=bearer_token
    )


@router.post("/view-as", status_code=201)
def start_view_as(
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    """Start a read-only View-as session. platform-api decides who may (SUPER_ADMIN with the permission)
    and whom (an active internal employee); this is a pass-through like every other admin call."""
    return call_platform_admin(platform, "POST", "/api/platform/admin/view-as", bearer_token=bearer_token, json=payload)


@router.post("/view-as/{session_id}/end")
def end_view_as(
    session_id: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "POST", f"/api/platform/admin/view-as/{session_id}/end", bearer_token=bearer_token
    )


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(platform, "GET", f"/api/platform/admin/users/{user_id}", bearer_token=bearer_token)


@router.get("/users/{user_id}/effective-access")
def get_effective_access(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "GET", f"/api/platform/admin/users/{user_id}/effective-access", bearer_token=bearer_token
    )


@router.get("/users/{user_id}/access-diagnostics")
def get_access_diagnostics(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "GET", f"/api/platform/admin/users/{user_id}/access-diagnostics", bearer_token=bearer_token
    )


@router.patch("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PATCH", f"/api/platform/admin/users/{user_id}/status", bearer_token=bearer_token, json=payload
    )


@router.patch("/users/{user_id}/platform-role")
def update_platform_role(
    user_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PATCH", f"/api/platform/admin/users/{user_id}/platform-role",
        bearer_token=bearer_token, json=payload,
    )


@router.put("/users/{user_id}/modules/{module_key}")
def upsert_module_assignment(
    user_id: int,
    module_key: str,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PUT", f"/api/platform/admin/users/{user_id}/modules/{module_key}",
        bearer_token=bearer_token, json=payload,
    )


def _break_glass(reason: str | None) -> dict | None:
    return {"break_glass_reason": reason} if reason else None


@router.delete("/users/{user_id}/modules/{module_key}")
def remove_module_assignment(
    user_id: int,
    module_key: str,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/users/{user_id}/modules/{module_key}", bearer_token=bearer_token,
        params=_break_glass(break_glass_reason),
    )


@router.post("/users/{user_id}/modules/{module_key}/restore-default")
def restore_default_access(
    user_id: int,
    module_key: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "POST", f"/api/platform/admin/users/{user_id}/modules/{module_key}/restore-default",
        bearer_token=bearer_token,
    )


@router.get("/clients")
def list_clients(
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    """Canonical client listing for the Admin Center's client-scope picker —
    forwarded to Platform Core, which owns Client identity (§6.1)."""
    return call_platform_admin(
        platform, "GET", "/api/platform/admin/clients", bearer_token=bearer_token
    )


@router.get("/modules")
def list_modules(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> list[dict]:
    return call_platform_admin(platform, "GET", "/api/platform/admin/modules", bearer_token=bearer_token)


@router.get("/roles")
def list_roles(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> list[dict]:
    return call_platform_admin(platform, "GET", "/api/platform/admin/roles", bearer_token=bearer_token)


@router.get("/permissions")
def list_permissions(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> list[dict]:
    return call_platform_admin(platform, "GET", "/api/platform/admin/permissions", bearer_token=bearer_token)


@router.get("/audit")
def list_audit(
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    params = {"entity_type": entity_type, "entity_id": entity_id, "user_id": user_id, "limit": limit}
    return call_platform_admin(
        platform, "GET", "/api/platform/admin/audit",
        bearer_token=bearer_token, params={k: v for k, v in params.items() if v is not None},
    )


# --- Access Groups (Phase 2.6) — pure pass-through, same pattern as every
# route above. No talent-api enrichment needed (client names are enriched
# only where client_ids surface, same as effective-access).


@router.get("/groups")
def list_groups(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> list[dict]:
    return call_platform_admin(platform, "GET", "/api/platform/admin/groups", bearer_token=bearer_token)


@router.post("/groups")
def create_group(
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "POST", "/api/platform/admin/groups", bearer_token=bearer_token, json=payload
    )


@router.get("/groups/{group_id}")
def get_group(
    group_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(platform, "GET", f"/api/platform/admin/groups/{group_id}", bearer_token=bearer_token)


@router.patch("/groups/{group_id}")
def update_group(
    group_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PATCH", f"/api/platform/admin/groups/{group_id}", bearer_token=bearer_token, json=payload
    )


@router.patch("/groups/{group_id}/status")
def set_group_status(
    group_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PATCH", f"/api/platform/admin/groups/{group_id}/status", bearer_token=bearer_token, json=payload
    )


@router.post("/groups/{group_id}/members")
def add_group_member(
    group_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "POST", f"/api/platform/admin/groups/{group_id}/members", bearer_token=bearer_token, json=payload
    )


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_group_member(
    group_id: int,
    user_id: int,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/groups/{group_id}/members/{user_id}", bearer_token=bearer_token,
        params=_break_glass(break_glass_reason),
    )


@router.put("/groups/{group_id}/modules/{module_key}")
def upsert_group_module_assignment(
    group_id: int,
    module_key: str,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PUT", f"/api/platform/admin/groups/{group_id}/modules/{module_key}",
        bearer_token=bearer_token, json=payload,
    )


@router.delete("/groups/{group_id}/modules/{module_key}")
def remove_group_module_assignment(
    group_id: int,
    module_key: str,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/groups/{group_id}/modules/{module_key}", bearer_token=bearer_token,
        params=_break_glass(break_glass_reason),
    )


@router.get("/applications/{module_key}")
def application_detail(
    module_key: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    detail = call_platform_admin(
        platform, "GET", f"/api/platform/admin/applications/{module_key}", bearer_token=bearer_token
    )
    return detail


# --- Delegated application access: administrators, suspensions, registry switch ----------------
# Authorization is re-derived by Platform Core from the caller's own token (Super Admin for
# appointments, manage_users for lifting a suspension, manage_modules for the registry).


@router.get("/applications/{module_key}/administrators")
def list_application_administrators(
    module_key: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    return call_platform_admin(
        platform, "GET", f"/api/platform/admin/applications/{module_key}/administrators", bearer_token=bearer_token
    )


@router.put("/applications/{module_key}/administrators/{user_id}")
def appoint_application_administrator(
    module_key: str,
    user_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PUT", f"/api/platform/admin/applications/{module_key}/administrators/{user_id}",
        bearer_token=bearer_token, json=payload,
    )


@router.delete("/applications/{module_key}/administrators/{user_id}")
def remove_application_administrator(
    module_key: str,
    user_id: int,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/applications/{module_key}/administrators/{user_id}",
        bearer_token=bearer_token, params=_break_glass(break_glass_reason),
    )


@router.get("/applications/{module_key}/suspensions")
def list_application_suspensions(
    module_key: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    return call_platform_admin(
        platform, "GET", f"/api/platform/admin/applications/{module_key}/suspensions", bearer_token=bearer_token
    )


@router.delete("/applications/{module_key}/suspensions/{user_id}")
def lift_application_suspension(
    module_key: str,
    user_id: int,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/applications/{module_key}/suspensions/{user_id}",
        bearer_token=bearer_token, params=_break_glass(break_glass_reason),
    )


@router.patch("/modules/{module_key}")
def set_module_enabled(
    module_key: str,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "PATCH", f"/api/platform/admin/modules/{module_key}", bearer_token=bearer_token, json=payload
    )


# --- Notifications (email outbox, owned by Platform Core) ---------------------------------------
# Pure pass-through: Platform Core authorizes every call from the caller's own token.


@router.get("/notifications/summary")
def notifications_summary(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> Response:
    return forward_platform_admin(platform, "GET", "/api/platform/admin/notifications/summary",
                                  bearer_token=bearer_token)


@router.get("/notifications/outbox")
def notifications_outbox(
    application: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    recipient: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    params = {"application": application, "event_type": event_type, "recipient": recipient, "status": status,
              "limit": limit, "offset": offset}
    return forward_platform_admin(platform, "GET", "/api/platform/admin/notifications/outbox",
                                  bearer_token=bearer_token, params={k: v for k, v in params.items() if v is not None})


@router.get("/notifications/recipients")
def notification_recipient_search(
    q: str = Query(min_length=2, max_length=64),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(platform, "GET", "/api/platform/admin/notifications/recipients",
                                  bearer_token=bearer_token, params={"q": q})


@router.get("/notifications/outbox/{outbox_id}")
def notification_detail(
    outbox_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(platform, "GET", f"/api/platform/admin/notifications/outbox/{outbox_id}",
                                  bearer_token=bearer_token)


@router.post("/notifications/outbox/{outbox_id}/retry")
def notification_retry(
    outbox_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(platform, "POST", f"/api/platform/admin/notifications/outbox/{outbox_id}/retry",
                                  bearer_token=bearer_token)


@router.post("/notifications/dispatch")
def notifications_dispatch(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> Response:
    return forward_platform_admin(platform, "POST", "/api/platform/admin/notifications/dispatch",
                                  bearer_token=bearer_token)


@router.get("/notifications/events")
def notification_events(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> Response:
    return forward_platform_admin(platform, "GET", "/api/platform/admin/notifications/events",
                                  bearer_token=bearer_token)


@router.put("/notifications/events/{event_type}")
def set_notification_event(
    event_type: str,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(platform, "PUT", f"/api/platform/admin/notifications/events/{event_type}",
                                  bearer_token=bearer_token, json=payload)


@router.get("/notifications/test-recipients")
def list_test_recipients(
    bearer_token: str = Depends(get_bearer_token), platform: PlatformClient = Depends(get_platform_client)
) -> Response:
    return forward_platform_admin(platform, "GET", "/api/platform/admin/notifications/test-recipients",
                                  bearer_token=bearer_token)


@router.post("/notifications/test-recipients", status_code=201)
def add_test_recipient(
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(platform, "POST", "/api/platform/admin/notifications/test-recipients",
                                  bearer_token=bearer_token, json=payload)


@router.delete("/notifications/test-recipients/{recipient_id}")
def remove_test_recipient(
    recipient_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> Response:
    return forward_platform_admin(platform, "DELETE",
                                  f"/api/platform/admin/notifications/test-recipients/{recipient_id}",
                                  bearer_token=bearer_token)
