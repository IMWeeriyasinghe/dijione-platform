import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.access_group import GroupModuleClientScope
from app.models.client import Client
from app.models.user import UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope

router = APIRouter(tags=["health"])
logger = logging.getLogger("platform-api.health")


@router.get("/health")
def health() -> dict:
    return {"service": "platform-api", "status": "healthy"}


@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)) -> dict:
    """Readiness probe for a deployed environment: database reachability,
    the applied migration revision, the active auth mode, and the
    client-scope integrity check — now a local join against the
    platform-owned ``clients`` table (Architecture Completion Plan §6.1)."""
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

    # --- client-scope integrity (local join, platform-owned clients) ---
    try:
        known_refs = {
            row for row in db.execute(select(Client.public_id)).scalars()
        }
        used_refs: set[str] = set()
        for model in (UserModuleClientScope, GroupModuleClientScope, UserModuleRole):
            used_refs |= {
                row
                for row in db.execute(
                    select(model.client_ref).where(model.client_ref.is_not(None))
                ).scalars()
            }
        orphans = sorted(used_refs - known_refs)
        if orphans:
            checks["client_scope_integrity"] = {"orphan_client_refs": orphans}
            logger.error(
                "client-scope integrity: %d client_ref value(s) do not resolve to a "
                "platform client: %s",
                len(orphans),
                orphans,
            )
            ok = False
        else:
            checks["client_scope_integrity"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["client_scope_integrity"] = f"error: {exc.__class__.__name__}"

    return {"service": "platform-api", "status": "healthy" if ok else "degraded", "checks": checks}
