"""Builds the signed authorization claims embedded in every access token
issued by Platform Core (Phase 2.5 CR §19-20).

talent-api / birthday-api / spark-api decode these claims locally (same
HS256 secret in dev, Entra JWKS-derived claims later) instead of calling
Platform Core synchronously on every request — see
``packages/auth-client-py``. The token's expiry (``jwt_expires_minutes``) is
the accepted staleness window for permission changes: a module-role edit in
the Admin Center takes effect the next time the affected user logs in or
their token refreshes, not instantly. This is a deliberate, documented
trade-off (CR §21), not an oversight.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.authorization_service import AuthorizationService


def build_claims(user: User, db: Session) -> dict:
    authz = AuthorizationService(db)
    repo = UserRepository(db)

    module_roles: dict[str, dict] = {}
    for mr in repo.module_roles_for(user.id):
        if not mr.enabled:
            continue
        client_ids = authz.client_scope_for(mr)
        module_roles[mr.module_key] = {
            "role": mr.role,
            "client_id": mr.client_id,
            "client_ids": client_ids,  # None == unrestricted (ALL_CLIENTS)
            "permissions": sorted(authz.module_role_permissions(mr)),
        }

    return {
        "is_active": user.is_active,
        "full_name": user.full_name,
        "email": user.email,
        "platform_role": user.platform_role,
        "platform_permissions": sorted(authz.platform_permissions(user)),
        "module_roles": module_roles,
    }
