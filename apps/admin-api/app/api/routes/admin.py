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

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_bearer_token
from app.services.platform_gateway import PlatformClient, call_platform_admin, get_platform_client
from app.services.talent_gateway import get_talent_client, pending_talent_requests

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/dashboard")
def get_dashboard(
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    dashboard = call_platform_admin(platform, "GET", "/api/platform/admin/dashboard", bearer_token=bearer_token)
    dashboard["pending_talent_requests"] = pending_talent_requests(talent)
    return dashboard


@router.get("/users")
def list_users(
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    return call_platform_admin(platform, "GET", "/api/platform/admin/users", bearer_token=bearer_token)


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


@router.delete("/users/{user_id}/modules/{module_key}")
def remove_module_assignment(
    user_id: int,
    module_key: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/users/{user_id}/modules/{module_key}", bearer_token=bearer_token
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
    limit: int = Query(default=200, le=500),
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> list[dict]:
    return call_platform_admin(
        platform, "GET", "/api/platform/admin/audit",
        bearer_token=bearer_token, params={"entity_type": entity_type, "limit": limit},
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
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/groups/{group_id}/members/{user_id}", bearer_token=bearer_token
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
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
) -> dict:
    return call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/groups/{group_id}/modules/{module_key}", bearer_token=bearer_token
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
