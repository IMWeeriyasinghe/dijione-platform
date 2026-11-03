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
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

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
            # A photo is only offered for an unambiguous directory match.
            "has_photo": bool(single and single.get("has_photo")),
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


def _match(row: dict, *, q: str | None = None, emp_code: str | None = None, department: str | None = None,
           identity_class: str | None = None, employment_status: str | None = None) -> bool:
    """Shared row filter. ``emp_code`` is exact, case-sensitive equality (the
    identity rule); ``q`` is a display-only search over name and code."""
    return (_search_hit(row, q)
            and (not emp_code or row["emp_code"] == emp_code)
            and (not department or (row.get("department") or "") == department)
            and (not identity_class or row.get("identity_class") == identity_class)
            and (not employment_status or (row.get("employment_status") or "") == employment_status))


def _review_hit(row: dict, review: str | None) -> bool:
    if review == "needs_review":
        return bool(row["flags"])
    if review == "no_flags":
        return not row["flags"]
    return not review or review in row["flags"]


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

EMPLOYEE_SORTS = {
    "events": lambda r: r["events"],
    "activity_days": lambda r: r["activity_days"],
    "review_flags": lambda r: r["review_flags"],
    "employee": lambda r: ((r.get("employee_name") or "~").lower(), r["emp_code"]),
    "last_activity": lambda r: r.get("last_activity_local") or "",
}
EXCEPTION_SORTS = {
    "date": lambda r: (r["local_date"], r.get("first_activity_utc") or ""),
    "employee": lambda r: ((r.get("employee_name") or "~").lower(), r["emp_code"]),
    "flags": lambda r: len(r["flags"]),
    "punch_count": lambda r: r["punch_count"],
}


def _sort_rows(rows: list[dict], sort: str, keys: dict) -> None:
    """In-place stable sort by ``field`` or ``-field`` (descending)."""
    field = sort.lstrip("-")
    if field in keys:
        rows.sort(key=keys[field], reverse=sort.startswith("-"))


def overview(db: Session, allowed, site_id: str, tz: str | None, day: date, directory: DirectorySnapshot,
             date_to: date | None = None) -> dict:
    """KPIs for one site-local day, or an inclusive range (``day``..``date_to``).
    Employee KPIs count distinct employees; ``review_breakdown`` counts
    employee-days per flag (for a single day the two are the same)."""
    ident = Identity(directory)
    end = date_to or day
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=day, date_to=end, directory=directory)
    breakdown = Counter(f for r in rows for f in r["flags"])

    def flagged(flag: str) -> int:
        return len({r["emp_code"] for r in rows if flag in r["flags"]})

    fresh = freshness(db, allowed_site_ids=(site_id,))
    site_fresh = fresh["sites"][0] if fresh["sites"] else {}
    return {
        "site_id": site_id, "date": day.isoformat(), "date_from": day.isoformat(), "date_to": end.isoformat(),
        "time_zone": tz,
        "directory_available": ident.available,
        "kpis": {
            "employees_with_activity": len({r["emp_code"] for r in rows}),
            "total_events": sum(r["punch_count"] for r in rows),
            "activity_days": len({r["local_date"] for r in rows}),
            "employees_needing_review": len({r["emp_code"] for r in rows if r["flags"]}),
            "single_punch_employees": flagged(ReviewFlag.SINGLE_PUNCH.value),
            "unmatched_codes": flagged(ReviewFlag.UNMATCHED_CODE.value),
            "feed_state": site_fresh.get("feed_state"),
        },
        "review_breakdown": {f: breakdown.get(f, 0) for f in REVIEW_FLAGS},
        "last_successful_sync_at": fresh["last_successful_sync_at"],
        "latest_received_utc": site_fresh.get("latest_received_utc"),
        "agent_heartbeat_utc": site_fresh.get("agent_heartbeat_utc"),
    }


def hourly(db: Session, allowed, site_id: str, day: date, date_to: date | None = None) -> dict:
    counts = {h: (e, p) for h, e, p in AttendanceRepository(db).hourly_counts(
        allowed_site_ids=allowed, site_id=site_id, local_date=day, date_to=date_to)}
    return {
        "site_id": site_id, "date": day.isoformat(), "date_from": day.isoformat(),
        "date_to": (date_to or day).isoformat(),
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


# Upper bound for one filtered event scan (the 92-day range cap keeps real
# selections far below this; exports apply their own, smaller limit).
_SCAN_LIMIT = 250_000


def hour_windows(start: date, end: date, hour: int, tz: str | None) -> list[tuple[datetime, datetime]]:
    """UTC [start, end) of one site-local clock hour on every date in the
    range — converted with the site's own time zone (Asia/Colombo has no DST;
    other zones are handled by zoneinfo)."""
    zone = ZoneInfo(tz) if tz else UTC
    out = []
    d = start
    while d <= end:
        local = datetime(d.year, d.month, d.day, hour, tzinfo=zone)
        begin = local.astimezone(UTC)
        out.append((begin.replace(tzinfo=None), (begin + timedelta(hours=1)).replace(tzinfo=None)))
        d += timedelta(days=1)
    return out


def select_activity(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot, *,
                    q: str | None, department: str | None, terminal: str | None, identity_class: str | None,
                    flag: str | None, tz: str | None, emp_code: str | None = None, offset: int = 0,
                    limit: int = 50, hour: int | None = None,
                    oldest_first: bool = False) -> tuple[int, list[AttendanceEvent]]:
    """The single Activity selection shared by the paged UI and the Excel
    export (newest first). Identity class and review flags are evaluated per
    employee-day — the same values each row displays — never per code."""
    repo = AttendanceRepository(db)
    ident = Identity(directory)
    codes = {emp_code} if emp_code else None
    if q or department:
        candidates = repo.distinct_codes(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end)
        if q:
            candidates = [c for c in candidates if _search_hit(ident.describe(c), q)]
        matched = ident.codes_matching(candidates, department=department, identity_class=None)
        codes = matched if codes is None else codes & matched
    tz_only = flag == ReviewFlag.TZ_INCONSISTENT.value
    day_flag = flag if flag and not tz_only else None
    windows = hour_windows(start, end, hour, tz) if hour is not None else None
    if not identity_class and not day_flag:
        return repo.events_page(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
                                emp_codes=codes, terminal=terminal, tz_inconsistent_only=tz_only,
                                offset=offset, limit=limit, utc_windows=windows, oldest_first=oldest_first)
    pairs = {(r["local_date"], r["emp_code"]) for r in daily_activity(
        db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz, date_from=start, date_to=end,
        directory=directory, emp_codes=codes)
        if (not identity_class or r["identity_class"] == identity_class) and (not day_flag or day_flag in r["flags"])}
    if not pairs:
        return 0, []
    scanned, events = repo.events_page(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
                                       emp_codes={c for _, c in pairs}, terminal=terminal,
                                       tz_inconsistent_only=tz_only, offset=0, limit=_SCAN_LIMIT,
                                       utc_windows=windows, oldest_first=oldest_first)
    if scanned > _SCAN_LIMIT:  # never silently drop rows
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Too much activity for these filters — "
                            "narrow the date range or add filters.")
    selected = [e for e in events if (e.site_local_date.isoformat(), e.emp_code) in pairs]
    return len(selected), selected[offset:offset + limit]


def activity(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot, *,
             q: str | None, department: str | None, terminal: str | None, identity_class: str | None,
             flag: str | None, page: int, page_size: int, technical: bool, tz: str | None = None,
             emp_code: str | None = None, hour: int | None = None, oldest_first: bool = False) -> dict:
    ident = Identity(directory)
    total, rows = select_activity(db, allowed, site_id, start, end, directory, q=q, department=department,
                                  terminal=terminal, identity_class=identity_class, flag=flag, tz=tz,
                                  emp_code=emp_code, offset=(page - 1) * page_size, limit=page_size,
                                  hour=hour, oldest_first=oldest_first)
    items = [_event_out(e, ident, technical=technical) for e in rows]
    # Review flags of each row's employee-day — computed for this page's rows only.
    if rows:
        days = {(r["local_date"], r["emp_code"]): r["flags"] for r in daily_activity(
            db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
            date_from=min(e.site_local_date for e in rows), date_to=max(e.site_local_date for e in rows),
            directory=directory, emp_codes={e.emp_code for e in rows})}
        for item in items:
            item["review_flags"] = days.get((item["local_date"], item["emp_code"]), [])
    return {"total": total, "page": page, "page_size": page_size, "directory_available": ident.available,
            "items": items}


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
               q: str | None, department: str | None, review: str | None, sort: str, page: int, page_size: int,
               emp_code: str | None = None, identity_class: str | None = None) -> dict:
    ident = Identity(directory)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=day, date_to=day, directory=directory)
    rows = [{**r, **{k: v for k, v in ident.describe(r["emp_code"], day, day).items() if k != "identity_class"}}
            for r in rows]
    departments = sorted({r["department"] for r in rows if r.get("department")})
    rows = [r for r in rows if _match(r, q=q, emp_code=emp_code, department=department, identity_class=identity_class)
            and _review_hit(r, review)]
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
              page: int, page_size: int, emp_code: str | None = None, identity_class: str | None = None,
              sort: str = "-events") -> dict:
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
                      "employment_status": e.get("employment_status"), "in_directory": True,
                      "has_photo": bool(e.get("has_photo")) and len(ident.index.get(code, [])) == 1}
    for code in act:  # attendance codes with no (or ambiguous) directory entry stay visible
        if code not in rows:
            d = ident.describe(code)
            rows[code] = {"emp_code": code, "employee_name": d["employee_name"], "department": d["department"],
                          "employment_status": d["employment_status"], "in_directory": False,
                          "has_photo": d["has_photo"]}
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
    out = [r for r in out if _match(r, q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                                    employment_status=status_filter)]
    summary = {  # the filtered population for the period, before the activity filter
        "employees": len(out),
        "with_activity": sum(1 for r in out if r["events"]),
        "active": sum(1 for r in out if (r.get("employment_status") or "").lower() == "active"),
        "inactive": sum(1 for r in out if (r.get("employment_status") or "").lower() == "inactive"),
        "not_in_directory": sum(1 for r in out if not r["in_directory"]),
        "needing_review": sum(1 for r in out if r["review_flags"]),
        "matched": sum(1 for r in out if (r.get("identity_class") or "").startswith("MATCHED")),
    }
    if activity_filter == "with_activity":
        out = [r for r in out if r["events"]]
    elif activity_filter == "no_activity":
        out = [r for r in out if not r["events"]]
    out.sort(key=lambda r: (r.get("employee_name") or "~", r["emp_code"]))  # stable tie-break
    _sort_rows(out, sort, EMPLOYEE_SORTS)
    return {**_page(out, page, page_size), "site_id": site_id, "date_from": start.isoformat(),
            "date_to": end.isoformat(), "departments": departments, "directory_available": ident.available,
            "summary": summary}


def employee_detail(db: Session, allowed, site_id: str, tz: str | None, code: str, start: date, end: date,
                    directory: DirectorySnapshot, *, technical: bool, include_events: bool = True) -> dict:
    repo = AttendanceRepository(db)
    ident = Identity(directory)
    days = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=start, date_to=end, directory=directory, emp_codes=[code])
    _with_terminals(db, allowed, site_id, start, end, days, [code])
    # Raw events are optional: the profile loads them per selected day via
    # /activity (paged) instead of downloading the whole period up front.
    events = repo.events_page(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
                              emp_codes=[code], offset=0, limit=2000)[1] if include_events else []
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
               *, flag: str | None, q: str | None, page: int, page_size: int, emp_code: str | None = None,
               department: str | None = None, identity_class: str | None = None, sort: str = "-date") -> dict:
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
                "employment_status": d["employment_status"], "has_photo": d["has_photo"],
                "reasons": [{"flag": f, "reason": _FLAG_REASON[f]} for f in r["flags"]]}
        if _match(item, q=q, emp_code=emp_code, department=department, identity_class=identity_class):
            items.append(item)
    items.sort(key=lambda r: (r["local_date"], r["first_activity_utc"]), reverse=True)
    _sort_rows(items, sort, EXCEPTION_SORTS)
    paged = _page(items, page, page_size)
    _with_terminals(db, allowed, site_id, start, end, paged["items"], {r["emp_code"] for r in paged["items"]})
    return {**paged, "site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(),
            "counts": {f: counts.get(f, 0) for f in REVIEW_FLAGS}, "directory_available": ident.available}


IDENTITY_CLASSES = [c.value for c in IdentityClass]
