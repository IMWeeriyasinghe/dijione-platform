"""Diji On-site Dashboard V1 — server-side assembly of the operational views.

Neutral facts only (first/latest activity, punch count, span, terminals,
needs-review flags). No Present/Absent/Late/Early/worked-hours judgements —
those need an approved attendance policy. ``PunchState`` is passed through
raw and never interpreted. Employee identity always comes from the people-api
Workforce Directory by exact EmpCode == Employee Number; when the directory is
unavailable every view still works with raw EmpCodes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import IdentityClass, ReviewFlag
from app.models.mirror import AttendanceEvent
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.site_repository import SiteRepository
from app.services.attendance_summary import daily_activity
from app.services.freshness_service import freshness
from app.services.identity_match_service import classify
from app.services.time_derivation import site_today, to_site_local
from app.services.workforce_directory import DirectorySnapshot

MAX_RANGE_DAYS = 92
REVIEW_FLAGS = [f.value for f in ReviewFlag]


# --- site / date resolution ------------------------------------------------


def resolve_site(db: Session, allowed_site_ids: Collection[str], site_id: str | None) -> tuple[str, str | None]:
    """The requested site if allowed (404 otherwise), else the first enabled
    site. No enabled site at all is a 404 the UI renders as an empty state."""
    allowed = sorted(allowed_site_ids)
    if site_id is not None:
        if site_id not in allowed_site_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
        chosen = site_id
    elif allowed:
        chosen = allowed[0]
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No enabled site")
    return chosen, SiteRepository(db).time_zones([chosen]).get(chosen)


def resolve_range(date_from: date | None, date_to: date | None, *, default_days: int, today: date) -> tuple[date, date]:
    end = date_to or today
    start = date_from or end - timedelta(days=default_days - 1)
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_from must not be after date_to")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Date range is limited to {MAX_RANGE_DAYS} days")
    return start, end


# --- identity enrichment ---------------------------------------------------


class Identity:
    def __init__(self, directory: DirectorySnapshot):
        self.available = directory.available
        self.entries = directory.entries if directory.available else []
        self.index = directory.by_employee_number() if directory.available else {}

    def describe(self, code: str, first: date | None = None, last: date | None = None) -> dict:
        matches = self.index.get(code, [])
        single = matches[0] if len(matches) == 1 else None
        cls = None
        if self.available:
            ref = last or first or date.today()
            cls = classify(matches, first or ref, ref).value
        return {
            "emp_code": code,
            "employee_name": single.get("display_name") if single else None,
            "department": single.get("department") if single else None,
            "employment_status": single.get("employment_status") if single else None,
            "identity_class": cls,
        }

    def codes_matching(self, codes: Collection[str], *, department: str | None, identity_class: str | None) -> set[str]:
        out = set()
        for code in codes:
            d = self.describe(code)
            if department and (d["department"] or "") != department:
                continue
            if identity_class and d["identity_class"] != identity_class:
                continue
            out.add(code)
        return out


def _search_hit(row: dict, q: str | None) -> bool:
    if not q:
        return True
    q = q.strip().lower()
    return q in row["emp_code"].lower() or q in (row.get("employee_name") or "").lower()


def _page(items: list, page: int, page_size: int) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size, "items": items[start:start + page_size]}


def _sites(db: Session, allowed_site_ids: Collection[str]) -> list[dict]:
    out = []
    for source, settings in SiteRepository(db).all_sites():
        if settings.site_id not in allowed_site_ids:
            continue
        tz = source.time_zone if source else None
        out.append({
            "site_id": settings.site_id,
            "name": settings.label or (source.display_name if source else settings.site_id),
            "time_zone": tz,
            "today": site_today(tz).isoformat(),
        })
    return out


def list_sites(db: Session, allowed_site_ids: Collection[str]) -> list[dict]:
    repo = AttendanceRepository(db)
    sites = _sites(db, allowed_site_ids)
    for s in sites:
        first, last = repo.date_bounds(allowed_site_ids=allowed_site_ids, site_id=s["site_id"])
        s["first_activity_date"] = first.isoformat() if first else None
        s["last_activity_date"] = last.isoformat() if last else None
        s["terminals"] = repo.terminal_names(allowed_site_ids=allowed_site_ids, site_id=s["site_id"])
    return sites


# --- views -----------------------------------------------------------------


def overview(db: Session, allowed, site_id: str, tz: str | None, day: date, directory: DirectorySnapshot) -> dict:
    ident = Identity(directory)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=day, date_to=day, directory=directory)
    breakdown = Counter(f for r in rows for f in r["flags"])
    fresh = freshness(db, allowed_site_ids=(site_id,))
    site_fresh = fresh["sites"][0] if fresh["sites"] else {}
    return {
        "site_id": site_id, "date": day.isoformat(), "time_zone": tz,
        "directory_available": ident.available,
        "kpis": {
            "employees_with_activity": len(rows),
            "total_events": sum(r["punch_count"] for r in rows),
            "employees_needing_review": sum(1 for r in rows if r["flags"]),
            "single_punch_employees": breakdown.get(ReviewFlag.SINGLE_PUNCH.value, 0),
            "unmatched_codes": breakdown.get(ReviewFlag.UNMATCHED_CODE.value, 0),
            "feed_state": site_fresh.get("feed_state"),
        },
        "review_breakdown": {f: breakdown.get(f, 0) for f in REVIEW_FLAGS},
        "last_successful_sync_at": fresh["last_successful_sync_at"],
        "latest_received_utc": site_fresh.get("latest_received_utc"),
        "agent_heartbeat_utc": site_fresh.get("agent_heartbeat_utc"),
    }


def hourly(db: Session, allowed, site_id: str, day: date) -> dict:
    counts = {h: (e, p) for h, e, p in AttendanceRepository(db).hourly_counts(
        allowed_site_ids=allowed, site_id=site_id, local_date=day)}
    return {
        "site_id": site_id, "date": day.isoformat(),
        "hours": [{"hour": h, "events": counts.get(f"{h:02d}", (0, 0))[0], "employees": counts.get(f"{h:02d}", (0, 0))[1]}
                  for h in range(24)],
    }


def trend(db: Session, allowed, site_id: str, start: date, end: date) -> dict:
    data = {d: (e, p) for d, e, p in AttendanceRepository(db).daily_trend(
        allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end)}
    days = []
    d = start
    while d <= end:
        e, p = data.get(d, (0, 0))
        days.append({"date": d.isoformat(), "events": e, "employees": p})
        d += timedelta(days=1)
    return {"site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(), "days": days}


def _event_out(e: AttendanceEvent, ident: Identity, *, technical: bool) -> dict:
    out = {
        **ident.describe(e.emp_code, e.site_local_date, e.site_local_date),
        "local_time": e.punch_time_local,
        "local_date": e.site_local_date.isoformat(),
        "terminal": e.terminal_alias,
        "area": e.area_alias,
        "punch_state_raw": e.punch_state,
        "tz_consistent": e.tz_consistent,
    }
    if technical:
        out.update({
            "event_id": e.event_id, "source_epoch": e.source_epoch,
            "source_transaction_id": e.source_transaction_id, "verify_type": e.verify_type,
            "terminal_sn": e.terminal_sn, "punch_time_utc": e.punch_time_utc.isoformat(),
            "received_utc": e.received_utc.isoformat(), "record_hash": e.record_hash,
        })
    return out


def activity(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot, *,
             q: str | None, department: str | None, terminal: str | None, identity_class: str | None,
             flag: str | None, page: int, page_size: int, technical: bool, tz: str | None = None) -> dict:
    repo = AttendanceRepository(db)
    ident = Identity(directory)
    codes = None
    if q or department or identity_class:
        candidates = repo.distinct_codes(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end)
        if q:
            candidates = [c for c in candidates if _search_hit(ident.describe(c), q)]
        codes = ident.codes_matching(candidates, department=department, identity_class=identity_class)
    if flag and flag != ReviewFlag.TZ_INCONSISTENT.value:
        flagged = {(r["emp_code"]) for r in daily_activity(
            db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz, date_from=start, date_to=end,
            directory=directory, emp_codes=codes) if flag in r["flags"]}
        codes = flagged if codes is None else codes & flagged
    total, rows = repo.events_page(
        allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end, emp_codes=codes, terminal=terminal,
        tz_inconsistent_only=flag == ReviewFlag.TZ_INCONSISTENT.value,
        offset=(page - 1) * page_size, limit=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "directory_available": ident.available,
            "items": [_event_out(e, ident, technical=technical) for e in rows]}


def _with_terminals(db, allowed, site_id, start, end, rows: list[dict], emp_codes=None) -> list[dict]:
    terms: dict[tuple[str, str], set[str]] = defaultdict(set)
    for d, code, t in AttendanceRepository(db).terminals_by_day(
        allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end, emp_codes=emp_codes,
    ):
        if t:
            terms[(d.isoformat(), code)].add(t)
    for r in rows:
        r["terminal_names"] = sorted(terms.get((r["local_date"], r["emp_code"]), set()))
    return rows


def today_view(db: Session, allowed, site_id: str, tz: str | None, day: date, directory: DirectorySnapshot, *,
               q: str | None, department: str | None, review: str | None, sort: str, page: int, page_size: int) -> dict:
    ident = Identity(directory)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=day, date_to=day, directory=directory)
    rows = [{**r, **{k: v for k, v in ident.describe(r["emp_code"], day, day).items() if k != "identity_class"}}
            for r in rows]
    departments = sorted({r["department"] for r in rows if r.get("department")})
    rows = [r for r in rows if _search_hit(r, q) and (not department or r.get("department") == department)]
    if review == "needs_review":
        rows = [r for r in rows if r["flags"]]
    elif review == "no_flags":
        rows = [r for r in rows if not r["flags"]]
    elif review:
        rows = [r for r in rows if review in r["flags"]]
    key, reverse = (sort.lstrip("-"), sort.startswith("-"))
    sort_keys = {
        "first_activity": lambda r: r["first_activity_utc"], "latest_activity": lambda r: r["latest_activity_utc"],
        "punch_count": lambda r: r["punch_count"], "span": lambda r: r["span_minutes"],
        "employee": lambda r: (r.get("employee_name") or "~", r["emp_code"]), "flags": lambda r: len(r["flags"]),
    }
    rows.sort(key=sort_keys.get(key, sort_keys["first_activity"]), reverse=reverse)
    paged = _page(rows, page, page_size)
    _with_terminals(db, allowed, site_id, day, day, paged["items"], {r["emp_code"] for r in paged["items"]})
    return {**paged, "site_id": site_id, "date": day.isoformat(), "departments": departments,
            "directory_available": ident.available}


def employees(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date, directory: DirectorySnapshot,
              *, q: str | None, department: str | None, status_filter: str | None, activity_filter: str | None,
              page: int, page_size: int) -> dict:
    repo = AttendanceRepository(db)
    ident = Identity(directory)
    act = {c: (n, days, last) for c, n, days, last in repo.employee_activity(
        allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end)}
    last_ever = repo.last_activity(allowed_site_ids=allowed, site_id=site_id)
    flags = Counter()
    for r in daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                            date_from=start, date_to=end, directory=directory):
        flags[r["emp_code"]] += len(r["flags"])

    rows: dict[str, dict] = {}
    for e in ident.entries:  # every workforce employee with an Employee Number
        code = e.get("employee_number")
        if code is None or not str(code).strip() or code in rows:
            continue
        rows[code] = {"emp_code": code, "employee_name": e.get("display_name"), "department": e.get("department"),
                      "employment_status": e.get("employment_status"), "in_directory": True}
    for code in act:  # attendance codes with no (or ambiguous) directory entry stay visible
        if code not in rows:
            d = ident.describe(code)
            rows[code] = {"emp_code": code, "employee_name": d["employee_name"], "department": d["department"],
                          "employment_status": d["employment_status"], "in_directory": False}
    out = []
    for code, r in rows.items():
        n, days, last = act.get(code, (0, 0, None))
        r.update({
            "events": n, "activity_days": days, "review_flags": flags.get(code, 0),
            "last_activity_local": to_site_local(last_ever.get(code), tz),
            "identity_class": ident.describe(code, start, end)["identity_class"],
        })
        out.append(r)
    departments = sorted({r["department"] for r in out if r.get("department")})
    out = [r for r in out if _search_hit(r, q) and (not department or r.get("department") == department)
           and (not status_filter or (r.get("employment_status") or "") == status_filter)]
    if activity_filter == "with_activity":
        out = [r for r in out if r["events"]]
    elif activity_filter == "no_activity":
        out = [r for r in out if not r["events"]]
    out.sort(key=lambda r: (-r["events"], r.get("employee_name") or "~", r["emp_code"]))
    return {**_page(out, page, page_size), "site_id": site_id, "date_from": start.isoformat(),
            "date_to": end.isoformat(), "departments": departments, "directory_available": ident.available}


def employee_detail(db: Session, allowed, site_id: str, tz: str | None, code: str, start: date, end: date,
                    directory: DirectorySnapshot, *, technical: bool) -> dict:
    repo = AttendanceRepository(db)
    ident = Identity(directory)
    days = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=start, date_to=end, directory=directory, emp_codes=[code])
    _with_terminals(db, allowed, site_id, start, end, days, [code])
    _, events = repo.events_page(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
                                 emp_codes=[code], offset=0, limit=2000)
    profile = ident.describe(code, start, end)
    matches = ident.index.get(code, [])
    if not days and not matches:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return {
        "site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(),
        "profile": {**profile, "job_title": matches[0].get("job_title") if len(matches) == 1 else None,
                    "match_count": len(matches)},
        "summary": {"activity_days": len(days), "events": sum(d["punch_count"] for d in days),
                    "review_flags": sum(len(d["flags"]) for d in days)},
        "days": sorted(days, key=lambda d: d["local_date"], reverse=True),
        "events": [_event_out(e, ident, technical=technical) for e in events],
        "directory_available": ident.available,
    }


_FLAG_REASON = {
    ReviewFlag.SINGLE_PUNCH.value: "Only one activity was recorded on this completed day.",
    ReviewFlag.HIGH_PUNCH_COUNT.value: "An unusually high number of activities was recorded on this day.",
    ReviewFlag.POSSIBLE_DUPLICATE_TAP.value: "Two activities were recorded within 60 seconds of each other.",
    ReviewFlag.UNMATCHED_CODE.value: "The Employee Code has no matching Employee Number in the Workforce Directory.",
    ReviewFlag.AMBIGUOUS_CODE.value: "More than one Workforce Directory employee has this Employee Number.",
    ReviewFlag.INACTIVE_EMPLOYEE_ACTIVITY.value: (
        "Activity is recorded for an employee who is inactive or past their termination date."
    ),
    ReviewFlag.BEFORE_HIRE_ACTIVITY.value: "Activity is recorded before the employee's hire date.",
    ReviewFlag.TZ_INCONSISTENT.value: "The source local time does not match the site's configured time zone.",
}


def exceptions(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date, directory: DirectorySnapshot,
               *, flag: str | None, q: str | None, page: int, page_size: int) -> dict:
    ident = Identity(directory)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=start, date_to=end, directory=directory)
    counts = Counter(f for r in rows for f in r["flags"])
    items = []
    for r in rows:
        if not r["flags"] or (flag and flag not in r["flags"]):
            continue
        d = ident.describe(r["emp_code"], date.fromisoformat(r["local_date"]), date.fromisoformat(r["local_date"]))
        item = {**r, "employee_name": d["employee_name"], "department": d["department"],
                "reasons": [{"flag": f, "reason": _FLAG_REASON[f]} for f in r["flags"]]}
        if _search_hit(item, q):
            items.append(item)
    items.sort(key=lambda r: (r["local_date"], r["first_activity_utc"]), reverse=True)
    paged = _page(items, page, page_size)
    _with_terminals(db, allowed, site_id, start, end, paged["items"], {r["emp_code"] for r in paged["items"]})
    return {**paged, "site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(),
            "counts": {f: counts.get(f, 0) for f in REVIEW_FLAGS}, "directory_available": ident.available}


IDENTITY_CLASSES = [c.value for c in IdentityClass]
