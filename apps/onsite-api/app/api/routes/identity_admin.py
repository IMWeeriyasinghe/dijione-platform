"""Identity Management API (backend of the existing /admin/identity page).

Reads require ``onsite.identity.read``; every write requires
``onsite.identity.manage`` (both ONSITE_ADMIN only). Everything is scoped to
the caller's enabled-site allow-list. Writes can be frozen with
``ONSITE_IDENTITY_WRITES_ENABLED=false`` (forward-only recovery).
Biometric-code investigation lives here, never on viewer routes.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import OnsiteScope, require_onsite_permission
from app.core.config import get_settings
from app.core.constants import Perm
from app.db.session import get_db
from app.services import identity_admin_service as ia
from app.services import identity_import_service as imp
from app.services import workforce_directory

router = APIRouter(prefix="/api/onsite/admin/identity", tags=["onsite-identity"])

_READ = require_onsite_permission(Perm.IDENTITY_READ)
_MANAGE = require_onsite_permission(Perm.IDENTITY_MANAGE)


def _actor(scope: OnsiteScope) -> ia.Actor:
    return ia.Actor(user_id=scope.user.id, allowed_site_ids=tuple(scope.allowed_site_ids))


def _writes_enabled() -> None:
    if not get_settings().onsite_identity_writes_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            {"error": "IDENTITY_WRITES_FROZEN",
                             "message": "Identity Management changes are temporarily disabled."})


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ia.IdentityError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None


def _page(items: list, page: int, page_size: int) -> dict:
    start = (page - 1) * page_size
    return {"total": len(items), "page": page, "page_size": page_size, "items": items[start:start + page_size]}


def _csv(rows: list[dict], cols: list[str], name: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if r.get(c) is None else (";".join(str(x.get("bamboohr_id")) for x in r[c])
                                                  if isinstance(r.get(c), list) else r.get(c)) for c in cols])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- request bodies ------------------------------------------------------------------


class MappingIn(BaseModel):
    site_id: str = Field(min_length=1, max_length=64)
    zk_emp_code: str = Field(min_length=1, max_length=20)
    bamboohr_id: str = Field(min_length=1, max_length=64)
    valid_from: date
    valid_to: date | None = None
    evidence: str
    acknowledged_warnings: list[str] = []

    def to_input(self) -> ia.MappingInput:
        return ia.MappingInput(site_id=self.site_id, zk_emp_code=self.zk_emp_code, bamboohr_id=self.bamboohr_id,
                               valid_from=self.valid_from, valid_to=self.valid_to, evidence=self.evidence,
                               acknowledged_warnings=tuple(self.acknowledged_warnings))


class CloseIn(BaseModel):
    valid_to: date
    reason: str


class ReplacementIn(BaseModel):
    bamboohr_id: str = Field(min_length=1, max_length=64)
    valid_from: date
    valid_to: date | None = None
    evidence: str
    acknowledged_warnings: list[str] = []


class CorrectIn(BaseModel):
    reason: str
    replacement: ReplacementIn | None = None


class ReassignNewOwnerIn(BaseModel):
    bamboohr_id: str = Field(min_length=1, max_length=64)
    valid_to: date | None = None
    evidence: str
    acknowledged_warnings: list[str] = []


class ReassignIn(BaseModel):
    site_id: str
    effective_from: date
    reason: str
    new: ReassignNewOwnerIn
    same_day_handling: str | None = Field(None, pattern="^(leave_unmapped|attribute_to_new|attribute_to_previous)$")


class RejectIn(BaseModel):
    site_id: str
    zk_emp_code: str = Field(min_length=1, max_length=20)
    bamboohr_id: str = Field(min_length=1, max_length=64)
    reason: str
    applies_from: date | None = None
    applies_to: date | None = None


class WithdrawIn(BaseModel):
    reason: str


# --- reads -------------------------------------------------------------------------------

UNMAPPED_COLUMNS = ["site_id", "zk_emp_code", "first_seen", "last_seen", "event_count", "activity_days",
                    "unmapped_events", "unmapped_days", "first_unmapped", "last_unmapped", "mapped_today",
                    "mapping_count", "hint_employee_number_matches"]
MAPPING_COLUMNS = ["id", "site_id", "zk_emp_code", "bamboohr_id", "employee_name", "employee_number", "valid_from",
                   "valid_to", "status", "source", "evidence", "verified_by_user_id", "verified_at",
                   "closed_reason", "superseded_reason", "superseded_by_id"]


@router.get("/unmapped")
def unmapped(site_id: str | None = None, q: str | None = None,
             sort: str = Query("-unmapped_events", pattern="^-?(unmapped_events|event_count|last_unmapped|first_seen|"
                                                       "zk_emp_code|unmapped_days)$"),
             page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
             fmt: str = Query("json", alias="format", pattern="^(json|csv)$"),
             scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    rows = _run(ia.unmapped_report, db, _actor(scope), workforce_directory.load(), site_id=site_id, q=q, sort=sort)
    if fmt == "csv":
        return _csv(rows, UNMAPPED_COLUMNS, "onsite-unmapped-zkbiotime-ids.csv")
    return _page(rows, page, page_size)


@router.get("/codes/{zk_emp_code}")
def code_detail(zk_emp_code: str, site_id: str, date_from: date | None = None, date_to: date | None = None,
                scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    return _run(ia.code_investigation, db, _actor(scope), workforce_directory.load(), site_id=site_id,
                code=zk_emp_code, date_from=date_from, date_to=date_to)


@router.get("/codes/{zk_emp_code}/evidence")
def code_evidence(zk_emp_code: str, site_id: str, bamboohr_id: str, proposed_from: date,
                  proposed_to: date | None = None, exclude_mapping_id: int | None = None,
                  scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    actor = _actor(scope)
    _run(ia._site, actor, site_id)
    warnings = ia.evidence_warnings(db, actor, workforce_directory.load(), site_id, zk_emp_code, bamboohr_id,
                                    proposed_from, proposed_to,
                                    exclude_ids=(exclude_mapping_id,) if exclude_mapping_id else ())
    return {"site_id": site_id, "zk_emp_code": zk_emp_code, "bamboohr_id": bamboohr_id,
            "proposed_from": proposed_from.isoformat(), "proposed_to": proposed_to.isoformat() if proposed_to else None,
            "warnings": warnings}


@router.get("/directory/search")
def directory_search(q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    return _page(_run(ia.directory_search, db, _actor(scope), workforce_directory.load(), q), page, page_size)


@router.get("/mappings")
def mappings(site_id: str | None = None, status_: str | None = Query(None, alias="status",
                                                                    pattern="^(VERIFIED|SUPERSEDED)$"),
             bamboohr_id: str | None = None, zk_emp_code: str | None = None,
             page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
             fmt: str = Query("json", alias="format", pattern="^(json|csv)$"),
             scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    rows = _run(ia.list_mappings, db, _actor(scope), workforce_directory.load(), site_id=site_id, status=status_,
                bamboohr_id=bamboohr_id, zk_emp_code=zk_emp_code)
    if fmt == "csv":
        return _csv(rows, MAPPING_COLUMNS, "onsite-identity-mappings.csv")
    return _page(rows, page, page_size)


@router.get("/mappings/{mapping_id}")
def mapping_detail(mapping_id: int, scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    return _run(ia.get_mapping, db, _actor(scope), workforce_directory.load(), mapping_id)


@router.get("/conflicts")
def conflicts(site_id: str | None = None, scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    return _run(ia.conflicts, db, _actor(scope), workforce_directory.load(), site_id=site_id)


@router.get("/coverage")
def coverage(site_id: str, date_from: date | None = None, date_to: date | None = None,
             scope: OnsiteScope = Depends(_READ), db: Session = Depends(get_db)):
    """Identity Management dashboard: ID/punch coverage, trend, top unmapped IDs."""
    from app.repositories.site_repository import SiteRepository
    from app.services.dashboard_service import resolve_range
    from app.services.time_derivation import site_today

    tz = SiteRepository(db).time_zones([site_id]).get(site_id)
    start, end = resolve_range(date_from, date_to, default_days=30, today=site_today(tz))
    return _run(ia.coverage, db, _actor(scope), workforce_directory.load(), site_id=site_id, date_from=start,
                date_to=end)


@router.get("/readiness")
def readiness(site_id: str, days: int = Query(30, ge=1, le=92), scope: OnsiteScope = Depends(_READ),
              db: Session = Depends(get_db)):
    return _run(ia.readiness, db, _actor(scope), workforce_directory.load(), site_id=site_id, days=days)


# --- writes -----------------------------------------------------------------------------


@router.post("/mappings", status_code=201, dependencies=[Depends(_writes_enabled)])
def create_mapping(payload: MappingIn, scope: OnsiteScope = Depends(_MANAGE), db: Session = Depends(get_db)):
    return _run(ia.create_mapping, db, _actor(scope), workforce_directory.load(), payload.to_input())


@router.post("/mappings/{mapping_id}/close", dependencies=[Depends(_writes_enabled)])
def close_mapping(mapping_id: int, payload: CloseIn, scope: OnsiteScope = Depends(_MANAGE),
                  db: Session = Depends(get_db)):
    return _run(ia.close_mapping, db, _actor(scope), workforce_directory.load(), mapping_id, payload.valid_to,
                payload.reason)


@router.post("/mappings/{mapping_id}/correct", dependencies=[Depends(_writes_enabled)])
def correct_mapping(mapping_id: int, payload: CorrectIn, scope: OnsiteScope = Depends(_MANAGE),
                    db: Session = Depends(get_db)):
    actor = _actor(scope)
    replacement = None
    if payload.replacement is not None:
        from app.repositories.identity_repository import IdentityRepository

        old = IdentityRepository(db).get_mapping(mapping_id, allowed_site_ids=actor.allowed_site_ids)
        if old is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, {"error": "NOT_FOUND", "message": "Mapping not found."})
        r = payload.replacement
        replacement = ia.MappingInput(site_id=old.site_id, zk_emp_code=old.zk_emp_code, bamboohr_id=r.bamboohr_id,
                                      valid_from=r.valid_from, valid_to=r.valid_to, evidence=r.evidence,
                                      acknowledged_warnings=tuple(r.acknowledged_warnings))
    return _run(ia.correct_mapping, db, actor, workforce_directory.load(), mapping_id, payload.reason, replacement)


@router.post("/codes/{zk_emp_code}/reassign", dependencies=[Depends(_writes_enabled)])
def reassign(zk_emp_code: str, payload: ReassignIn, scope: OnsiteScope = Depends(_MANAGE),
             db: Session = Depends(get_db)):
    return _run(ia.reassign_code, db, _actor(scope), workforce_directory.load(), site_id=payload.site_id,
                zk_emp_code=zk_emp_code, effective_from=payload.effective_from, reason=payload.reason,
                new_bamboohr_id=payload.new.bamboohr_id, new_valid_to=payload.new.valid_to,
                new_evidence=payload.new.evidence, acknowledged_warnings=payload.new.acknowledged_warnings,
                same_day_handling=payload.same_day_handling)


@router.post("/rejections", status_code=201, dependencies=[Depends(_writes_enabled)])
def reject(payload: RejectIn, scope: OnsiteScope = Depends(_MANAGE), db: Session = Depends(get_db)):
    return _run(ia.reject, db, _actor(scope), workforce_directory.load(), site_id=payload.site_id,
                zk_emp_code=payload.zk_emp_code, bamboohr_id=payload.bamboohr_id, reason=payload.reason,
                applies_from=payload.applies_from, applies_to=payload.applies_to)


@router.post("/rejections/{rejection_id}/withdraw", dependencies=[Depends(_writes_enabled)])
def withdraw(rejection_id: int, payload: WithdrawIn, scope: OnsiteScope = Depends(_MANAGE),
             db: Session = Depends(get_db)):
    return _run(ia.withdraw_rejection, db, _actor(scope), rejection_id, payload.reason)


@router.post("/import", dependencies=[Depends(_writes_enabled)])
async def import_mappings(file: UploadFile = File(...), dry_run: bool = Query(True),
                          dry_run_token: str | None = Form(None), acknowledge_warnings: bool = Form(False),
                          scope: OnsiteScope = Depends(_MANAGE), db: Session = Depends(get_db)):
    content = await file.read()
    if dry_run:
        return _run(imp.dry_run, db, _actor(scope), workforce_directory.load(), content)
    return _run(imp.apply, db, _actor(scope), workforce_directory.load(), content, token=dry_run_token,
                acknowledge_warnings=acknowledge_warnings)
