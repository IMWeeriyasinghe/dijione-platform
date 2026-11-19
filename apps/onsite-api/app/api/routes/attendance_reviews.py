"""Attendance review cases (v0.9). Reads: ``onsite.exceptions.read`` (On-site
User and Admin). Every write: ``onsite.exceptions.manage`` (On-site Admin
only — there is no employee self-submission). Site-scoped: a case at a site
outside the caller's enabled-site allow-list is a 404. Writes are frozen with
ONSITE_REVIEW_WRITES_ENABLED=false (503); reads keep working."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import OnsiteScope, require_onsite_permission
from app.core.config import get_settings
from app.core.constants import Perm
from app.db.session import get_db
from app.services import attendance_review_service as rv
from app.services import dashboard_service as svc
from app.services import workforce_directory
from app.services.identity_resolution import MappingIndex
from app.services.time_derivation import site_today

router = APIRouter(prefix="/api/onsite/reviews", tags=["onsite-reviews"])

ExceptionType = Literal["SINGLE_RECORDED_FINGERPRINT", "DEPARTURE_TIME_QUERY", "DISPUTED_SPAN", "DEVICE_ISSUE",
                        "IDENTITY_ISSUE", "OTHER"]
Reason = Literal["FORGOT_TO_RECORD", "DEVICE_FAULT", "ASSIGNED_OFF_SITE", "APPROVED_LEAVE_OR_DUTY", "OTHER"]
Source = Literal["TEAM_MEMBER_STATEMENT", "MANAGER_CONFIRMATION", "SECURITY_OR_VISITOR_LOG", "OTHER"]
Outcome = Literal["JUSTIFIED", "NO_FURTHER_ACTION", "NOT_JUSTIFIED"]
_STATUS_FILTER = "^(OPEN|SUBMITTED|RESOLVED|REOPENED|NEEDS_REASSESSMENT)$"


def _writes_enabled() -> None:
    if not get_settings().onsite_review_writes_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Attendance review changes are temporarily disabled (read-only).")


class OpenIn(BaseModel):
    site_id: str = Field(min_length=1, max_length=64)
    local_date: date
    bamboohr_id: str | None = Field(None, max_length=64)
    zk_emp_code: str | None = Field(None, max_length=20)
    exception_type: ExceptionType
    note: str | None = Field(None, max_length=2000)


class SubmitIn(BaseModel):
    expected_version: int = Field(ge=1)
    justification_reason: Reason
    explanation: str = Field(min_length=10, max_length=4000)
    declared_departure_local: str | None = Field(None, max_length=40)
    declaration_source: Source | None = None
    evidence_reference: str | None = Field(None, max_length=300)


class ResolveIn(BaseModel):
    expected_version: int = Field(ge=1)
    outcome: Outcome
    decision_note: str = Field(min_length=10, max_length=4000)


class ReopenIn(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=4000)


def _ctx(db: Session, scope: OnsiteScope, site_id: str):
    site, tz = svc.resolve_site(db, scope.allowed_site_ids, site_id)
    index = MappingIndex.load(db, allowed_site_ids=scope.allowed_site_ids, directory=workforce_directory.load())
    return site, tz, index


def _detail(db: Session, scope: OnsiteScope, case, tz, index) -> dict:
    current = rv.day_facts(db, scope.allowed_site_ids, case.site_id, tz, index, case.local_date, case.identity_key)
    return {"case": rv.serialize(case, rv.evaluate(case, current)), "history": rv.history(db, case.id),
            "current_facts": current["facts"], "punches": current["punches"],
            "can_manage": scope.has(Perm.EXCEPTIONS_MANAGE)}


@router.get("")
def list_reviews(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
                 status_: str | None = Query(None, alias="status", pattern=_STATUS_FILTER),
                 exception_type: ExceptionType | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                 scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_READ)),
                 db: Session = Depends(get_db)):
    site, tz, index = _ctx(db, scope, site_id)
    start, end = svc.resolve_range(date_from, date_to, default_days=30, today=site_today(tz))
    items = []
    for case in rv.cases_in_range(db, site, start, end):
        if exception_type and case.exception_type != exception_type:
            continue
        ev = rv.evaluate(case, rv.day_facts(db, scope.allowed_site_ids, site, tz, index, case.local_date,
                                            case.identity_key))
        if status_ == "NEEDS_REASSESSMENT" and not ev["stale"]:
            continue
        if status_ and status_ != "NEEDS_REASSESSMENT" and case.status != status_:
            continue
        items.append(rv.serialize(case, ev))
    items.sort(key=lambda c: (c["local_date"], c["id"]), reverse=True)
    counts = {s: sum(1 for c in items if c["status"] == s) for s in ("OPEN", "SUBMITTED", "RESOLVED", "REOPENED")}
    return {**svc._page(items, page, page_size), "site_id": site, "date_from": start.isoformat(),
            "date_to": end.isoformat(), "counts": counts, "can_manage": scope.has(Perm.EXCEPTIONS_MANAGE)}


@router.get("/day")
def review_day(site_id: str, date_: date = Query(alias="date"), bamboohr_id: str | None = None,
               zk_emp_code: str | None = None,
               scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_READ)),
               db: Session = Depends(get_db)):
    """One identity-day: the case (or none), its history, the current facts and
    every recorded fingerprint of the day with its sequence."""
    if bool(bamboohr_id) == bool(zk_emp_code):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give exactly one of bamboohr_id or zk_emp_code")
    site, tz, index = _ctx(db, scope, site_id)
    key = f"P:{bamboohr_id}" if bamboohr_id else f"C:{zk_emp_code}"
    case = rv.find(db, site, date_, key)
    if case is not None:
        return _detail(db, scope, case, tz, index)
    current = rv.day_facts(db, scope.allowed_site_ids, site, tz, index, date_, key)
    return {"case": None, "history": [], "current_facts": current["facts"], "punches": current["punches"],
            "identity": current["identity"], "can_manage": scope.has(Perm.EXCEPTIONS_MANAGE)}


@router.get("/{case_id}")
def get_review(case_id: int, scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_READ)),
               db: Session = Depends(get_db)):
    case = rv.get_in_scope(db, scope.allowed_site_ids, case_id)
    _site, tz, index = _ctx(db, scope, case.site_id)
    return _detail(db, scope, case, tz, index)


@router.post("", dependencies=[Depends(_writes_enabled)])
def open_review(body: OpenIn, scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_MANAGE)),
                db: Session = Depends(get_db)):
    site, tz, index = _ctx(db, scope, body.site_id)
    case, created = rv.open_case(db, scope.allowed_site_ids, site, tz, index, actor=scope.user, day=body.local_date,
                                 bamboohr_id=body.bamboohr_id, zk_emp_code=body.zk_emp_code,
                                 exception_type=body.exception_type, note=body.note)
    return {**_detail(db, scope, case, tz, index), "created": created}


@router.post("/{case_id}/submit", dependencies=[Depends(_writes_enabled)])
def submit_review(case_id: int, body: SubmitIn,
                  scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_MANAGE)),
                  db: Session = Depends(get_db)):
    case = rv.get_in_scope(db, scope.allowed_site_ids, case_id)
    _site, tz, index = _ctx(db, scope, case.site_id)
    case = rv.submit(db, scope.allowed_site_ids, case, tz, index, actor=scope.user,
                     expected_version=body.expected_version, reason=body.justification_reason,
                     explanation=body.explanation, declared_departure_local=body.declared_departure_local,
                     declaration_source=body.declaration_source, evidence_reference=body.evidence_reference)
    return _detail(db, scope, case, tz, index)


@router.post("/{case_id}/resolve", dependencies=[Depends(_writes_enabled)])
def resolve_review(case_id: int, body: ResolveIn,
                   scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_MANAGE)),
                   db: Session = Depends(get_db)):
    case = rv.get_in_scope(db, scope.allowed_site_ids, case_id)
    _site, tz, index = _ctx(db, scope, case.site_id)
    case = rv.resolve(db, scope.allowed_site_ids, case, tz, index, actor=scope.user,
                      expected_version=body.expected_version, outcome=body.outcome, decision_note=body.decision_note)
    return _detail(db, scope, case, tz, index)


@router.post("/{case_id}/reopen", dependencies=[Depends(_writes_enabled)])
def reopen_review(case_id: int, body: ReopenIn,
                  scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_MANAGE)),
                  db: Session = Depends(get_db)):
    case = rv.get_in_scope(db, scope.allowed_site_ids, case_id)
    _site, tz, index = _ctx(db, scope, case.site_id)
    case = rv.reopen(db, scope.allowed_site_ids, case, tz, index, actor=scope.user,
                     expected_version=body.expected_version, reason=body.reason)
    return _detail(db, scope, case, tz, index)
