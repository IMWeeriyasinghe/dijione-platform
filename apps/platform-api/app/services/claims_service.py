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
from app.services.authorization_service import AuthorizationService


def build_claims(user: User, db: Session) -> dict:
    """Phase 2.6: ``module_roles`` now resolves through the combined
    direct+group ``AuthorizationService`` methods, so access granted purely
    via an Access Group flows into the JWT exactly like a direct assignment
    always has (CR §51).

    Ambiguity note: a user can have multiple contributing grants for the
    same module with *different* role keys (e.g. a direct TA_MEMBER
    assignment plus a GROUP grant of TA_MANAGER). The additive-ALLOW model
    has no natural single "the" role in that case. We keep the legacy
    single ``role``/``client_id`` claim fields backward compatible by
    picking one grant deterministically — a DIRECT grant if the user has
    one (preserves pre-Phase-2.6 behavior exactly for anyone who was never
    touched by groups), otherwise the first GROUP grant — while
    ``client_ids``/``permissions`` always reflect the full union across
    every contributing grant, direct and group alike, so no access is
    silently dropped from what a service can actually authorize.
    """
    authz = AuthorizationService(db)

    module_roles: dict[str, dict] = {}
    for module_key, grants in authz.effective_module_roles(user).items():
        primary = next((g for g in grants if g.source_type == "DIRECT"), grants[0])
        client_ids, _sources = authz.effective_client_scope(user, module_key)
        legacy_client_id = client_ids[0] if client_ids and len(client_ids) == 1 else None
        module_roles[module_key] = {
            "role": primary.role,
            "client_id": legacy_client_id,
            "client_ids": client_ids,  # None == unrestricted (ALL_CLIENTS)
            "permissions": sorted(authz.effective_permissions(user, module_key)),
        }

    return {
        "is_active": user.is_active,
        "full_name": user.full_name,
        "email": user.email,
        "platform_role": user.platform_role,
        "platform_permissions": sorted(authz.platform_permissions(user)),
        "module_roles": module_roles,
    }
