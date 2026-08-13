"""DijiOne Admin Center API — public contract unchanged from the pre-split
``apps/api``'s ``/api/admin/*`` (admin-web calls these exact paths/shapes).

Internally this is now a thin orchestrator: identity/role/module-registry/
audit mutations forward to Platform Core with the caller's own bearer token
(``platform_gateway``); DijiTalentFlow client names and the live pending-
request count are enriched in from talent-api (``talent_gateway``), best-
effort, since a TalentFlow outage should not break user administration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_bearer_token
from app.services.platform_gateway import PlatformClient, call_platform_admin, get_platform_client
from app.services.talent_gateway import (
    client_names_map,
    clients_lite_list,
    get_talent_client,
    pending_talent_requests,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _enrich_user(user: dict, names: dict[int, str]) -> dict:
    for assignment in user.get("module_assignments", []):
        scope = assignment.get("client_scope")
        if scope and scope.get("client_ids"):
            scope["client_names"] = [names.get(cid, str(cid)) for cid in scope["client_ids"]]
    return user


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
    talent: PlatformClient = Depends(get_talent_client),
) -> list[dict]:
    users = call_platform_admin(platform, "GET", "/api/platform/admin/users", bearer_token=bearer_token)
    names = client_names_map(talent)
    return [_enrich_user(u, names) for u in users]


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    user = call_platform_admin(platform, "GET", f"/api/platform/admin/users/{user_id}", bearer_token=bearer_token)
    return _enrich_user(user, client_names_map(talent))


@router.get("/users/{user_id}/effective-access")
def get_effective_access(
    user_id: int,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    access = call_platform_admin(
        platform, "GET", f"/api/platform/admin/users/{user_id}/effective-access", bearer_token=bearer_token
    )
    names = client_names_map(talent)
    for module in access.get("modules", []):
        scope = module.get("client_scope")
        if scope and scope.get("client_ids"):
            scope["client_names"] = [names.get(cid, str(cid)) for cid in scope["client_ids"]]
    return access


@router.patch("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    user = call_platform_admin(
        platform, "PATCH", f"/api/platform/admin/users/{user_id}/status", bearer_token=bearer_token, json=payload
    )
    return _enrich_user(user, client_names_map(talent))


@router.patch("/users/{user_id}/platform-role")
def update_platform_role(
    user_id: int,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    user = call_platform_admin(
        platform, "PATCH", f"/api/platform/admin/users/{user_id}/platform-role",
        bearer_token=bearer_token, json=payload,
    )
    return _enrich_user(user, client_names_map(talent))


@router.put("/users/{user_id}/modules/{module_key}")
def upsert_module_assignment(
    user_id: int,
    module_key: str,
    payload: dict,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    user = call_platform_admin(
        platform, "PUT", f"/api/platform/admin/users/{user_id}/modules/{module_key}",
        bearer_token=bearer_token, json=payload,
    )
    return _enrich_user(user, client_names_map(talent))


@router.delete("/users/{user_id}/modules/{module_key}")
def remove_module_assignment(
    user_id: int,
    module_key: str,
    bearer_token: str = Depends(get_bearer_token),
    platform: PlatformClient = Depends(get_platform_client),
    talent: PlatformClient = Depends(get_talent_client),
) -> dict:
    user = call_platform_admin(
        platform, "DELETE", f"/api/platform/admin/users/{user_id}/modules/{module_key}", bearer_token=bearer_token
    )
    return _enrich_user(user, client_names_map(talent))


@router.get("/clients")
def list_clients(
    _bearer_token: str = Depends(get_bearer_token),
    talent: PlatformClient = Depends(get_talent_client),
) -> list[dict]:
    """Lightweight client listing for the Admin Center's client-scope
    picker — talent-api owns Client now, so this is a pure forward."""
    return clients_lite_list(talent)


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
