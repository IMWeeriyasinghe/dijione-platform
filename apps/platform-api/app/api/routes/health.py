import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.access_group import GroupModuleClientScope
from app.models.user_module_client_scope import UserModuleClientScope
from app.services import client_directory

router = APIRouter(tags=["health"])
logger = logging.getLogger("platform-api.health")


@router.get("/health")
def health() -> dict:
    return {"service": "platform-api", "status": "healthy"}


@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)) -> dict:
    """Readiness probe for a deployed environment: database reachability,
    the applied migration revision, the active auth mode, and the temporary
    cross-service client-scope integrity check (Architecture v2 §9)."""
    settings = get_settings()
    checks: dict[str, object] = {}
    ok = True

    # --- database ---
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False

    # --- applied migration revision ---
    try:
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        checks["migration_revision"] = rev or "none"
    except Exception:  # noqa: BLE001
        checks["migration_revision"] = "unknown"

    # --- auth mode ---
    checks["auth_mode"] = "dev" if settings.dev_identity_mode else "entra"

    # --- client-scope integrity (temporary guard) ---
    try:
        scope_ids = {
            row
            for row in db.execute(
                select(UserModuleClientScope.client_id).where(
                    UserModuleClientScope.client_id.is_not(None)
                )
            ).scalars()
        }
        scope_ids |= {
            row
            for row in db.execute(
                select(GroupModuleClientScope.client_id).where(
                    GroupModuleClientScope.client_id.is_not(None)
                )
            ).scalars()
        }
        if not scope_ids:
            checks["client_scope_integrity"] = "ok"
        else:
            known = client_directory.known_client_ids()
            orphans = sorted(scope_ids - known)
            if orphans:
                checks["client_scope_integrity"] = {"orphan_client_ids": orphans}
                logger.error(
                    "client-scope integrity: %d client-scope id(s) do not resolve "
                    "against talent-api: %s",
                    len(orphans),
                    orphans,
                )
                ok = False
            else:
                checks["client_scope_integrity"] = "ok"
    except httpx.HTTPError:
        # talent-api unreachable — diagnostic only, does not fail readiness.
        checks["client_scope_integrity"] = "unavailable"
    except Exception as exc:  # noqa: BLE001
        checks["client_scope_integrity"] = f"error: {exc.__class__.__name__}"

    return {"service": "platform-api", "status": "healthy" if ok else "degraded", "checks": checks}
