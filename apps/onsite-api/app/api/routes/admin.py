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

from app.api.deps import OnsiteScope, require_onsite_permission
from app.core.constants import Perm
from app.db.session import get_db
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.site_repository import SiteRepository
from app.services import platform_audit, workforce_directory
from app.services.freshness_service import freshness
from app.services.identity_match_service import CSV_COLUMNS, build_report, csv_rows
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
    latest = MirrorSyncService(db).last_successful()
    data["reconciliation"] = json.loads(latest.reconciliation_json) if latest and latest.reconciliation_json else []
    return data


@router.get("/identity-match")
def identity_match(fmt: str = Query("json", alias="format", pattern="^(json|csv)$"),
                   scope: OnsiteScope = Depends(require_onsite_permission(Perm.IDENTITY_READ)),
                   db: Session = Depends(get_db)):
    activity = AttendanceRepository(db).emp_code_activity(allowed_site_ids=scope.allowed_site_ids)
    report = build_report(activity, workforce_directory.load())
    if fmt == "json":
        return report
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    writer.writerows(csv_rows(report))
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="onsite-identity-match.csv"'})
