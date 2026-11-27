"""On-site administration: sites (enable/disable, fail closed), site health
with reconciliation, and the identity match report."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import OnsiteScope, require_internal_service, require_onsite_permission
from app.core.constants import Perm
from app.db.session import get_db
from app.repositories.site_repository import SiteRepository
from app.services import mapping_date_correction, platform_audit, workforce_directory
from app.services.freshness_service import freshness
from app.services.legacy_contract import CSV_COLUMNS, csv_rows, identity_match_report, require_legacy_contract
from app.services.mirror_sync_service import MirrorSyncService

router = APIRouter(prefix="/api/onsite/admin", tags=["onsite-admin"])


class SiteUpdateIn(BaseModel):
    enabled: bool | None = None
    label: str | None = None
    expected_location_values: str | None = None


def _site_out(source, settings) -> dict:
    return {
        "site_id": settings.site_id, "enabled": settings.enabled,
        "label": settings.label, "display_name": source.display_name if source else None,
        "time_zone": source.time_zone if source else None, "source_active": source.is_active if source else None,
        "expected_location_values": settings.expected_location_values,
        "last_seen_at": source.last_seen_at.isoformat() if source and source.last_seen_at else None,
    }


@router.get("/sites")
def list_sites(_s: OnsiteScope = Depends(require_onsite_permission(Perm.SITES_MANAGE)),
               db: Session = Depends(get_db)) -> list[dict]:
    return [_site_out(src, st) for src, st in SiteRepository(db).all_sites()]


@router.get("/sites/{site_id}")
def get_site(site_id: str, _s: OnsiteScope = Depends(require_onsite_permission(Perm.SITES_MANAGE)),
             db: Session = Depends(get_db)) -> dict:
    found = SiteRepository(db).get(site_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return _site_out(*found)


@router.put("/sites/{site_id}")
def update_site(site_id: str, payload: SiteUpdateIn,
                scope: OnsiteScope = Depends(require_onsite_permission(Perm.SITES_MANAGE)),
                db: Session = Depends(get_db)) -> dict:
    found = SiteRepository(db).get(site_id)
    if found is None:  # only sites discovered from the source can be configured
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    source, settings = found
    before = _site_out(source, settings)
    for field in ("enabled", "label", "expected_location_values"):
        value = getattr(payload, field)
        if value is not None:
            setattr(settings, field, value)
    settings.updated_by_user_id = scope.user.id
    db.commit()
    after = _site_out(source, settings)
    action = ("onsite.site.enabled" if after["enabled"] else "onsite.site.disabled") \
        if before["enabled"] != after["enabled"] else "onsite.site.updated"
    platform_audit.record(actor_id=scope.user.id, action=action, entity_id=settings.id, previous=before, new=after)
    return after


@router.get("/health")
def site_health(scope: OnsiteScope = Depends(require_onsite_permission(Perm.HEALTH_READ)),
                db: Session = Depends(get_db)) -> dict:
    data = freshness(db, allowed_site_ids=scope.allowed_site_ids, technical=True)
    latest = MirrorSyncService(db).last_reconciled()
    data["reconciliation"] = json.loads(latest.reconciliation_json) if latest and latest.reconciliation_json else []
    return data


@router.get("/identity-match", dependencies=[Depends(require_legacy_contract)])
def identity_match(fmt: str = Query("json", alias="format", pattern="^(json|csv)$"),
                   identity_class: str | None = None, q: str | None = None,
                   page: int | None = Query(None, ge=1), page_size: int = Query(10, ge=1, le=200),
                   scope: OnsiteScope = Depends(require_onsite_permission(Perm.IDENTITY_READ)),
                   db: Session = Depends(get_db)):
    # LEGACY shape, verified-mapping semantics (see services/legacy_contract.py).
    report = identity_match_report(db, scope.allowed_site_ids, workforce_directory.load())
    if fmt == "json":
        if page is None:  # legacy: whole report (small; kept for compatibility)
            return report
        rows = [r for r in report["rows"] if (not identity_class or r["identity_class"] == identity_class)
                and (not q or q.lower() in r["emp_code"].lower()
                     or any(q.lower() in (m.get("display_name") or "").lower() for m in r["matches"]))]
        start = (page - 1) * page_size
        return {**report, "rows": rows[start:start + page_size], "total": len(rows), "page": page,
                "page_size": page_size}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    writer.writerows(csv_rows(report))
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="onsite-identity-match.csv"'})


# ── One-time hire-date alignment (internal service only) ───────────────────────

internal_router = APIRouter(
    prefix="/api/onsite/internal/ops", tags=["onsite-admin-internal"],
    dependencies=[Depends(require_internal_service)],
)


@internal_router.post("/correct-mapping-dates", status_code=200)
def correct_mapping_dates(
    dry_run: bool = Query(True, description="Set false to commit corrections"),
    db: Session = Depends(get_db),
) -> dict:
    """One-time hire-date alignment correction.

    Returns an inventory and correction report. Defaults to dry_run=True.
    Set dry_run=false to commit the approved corrections.
    Requires internal service token (X-Internal-Token header).
    """
    report = mapping_date_correction.run(db, dry_run=dry_run)
    return {
        "generated_at": report.generated_at,
        "dry_run": report.dry_run,
        "total_verified_open": report.total_verified_open,
        "already_aligned": report.already_aligned,
        "hire_date_missing": report.hire_date_missing,
        "hire_date_after_current": report.hire_date_after_current,
        "conflict_detected": report.conflict_detected,
        "historical_reassignment": report.historical_reassignment,
        "corrected": report.corrected,
        "rows": [
            {
                "mapping_id": r.mapping_id,
                "site_id": r.site_id,
                "zk_emp_code": r.zk_emp_code,
                "bamboohr_id": r.bamboohr_id,
                "current_valid_from": r.current_valid_from,
                "hire_date": r.hire_date,
                "proposed_valid_from": r.proposed_valid_from,
                "action": r.action,
                "skip_reason": r.skip_reason,
                "new_mapping_id": r.new_mapping_id,
            }
            for r in report.rows
        ],
    }
