"""Diji On-site Dashboard V1 — server-side assembly of the operational views.

Neutral facts only (first/latest activity, punch count, span, terminals,
needs-review flags). No Present/Absent/Late/Early/worked-hours judgements —
those need an approved attendance policy. ``PunchState`` is passed through
raw and never interpreted. Employee identity comes ONLY from administrator-
verified ZKBioTime ID -> BambooHR mappings (``identity_resolution``); unmapped
attendance is excluded from these viewer records (it stays visible in Identity
Management). Headcounts count distinct BambooHR employees, never codes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import IdentityClass, MappingStatus, ReviewFlag
from app.models.mirror import AttendanceEvent
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.site_repository import SiteRepository
from app.services.attendance_summary import daily_activity, identity_fields
from app.services.freshness_service import freshness
from app.services.identity_resolution import MappingIndex, legacy_identity_class
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


# --- identity -----------------------------------------------------------------


class Identity:
    """Verified identity for one request: mapping index + Workforce Directory.

    ``describe`` keeps the pre-redesign shape (legacy contract) and adds the
    new-contract keys. An unverified ZKBioTime ID describes as nobody — no
    name, department, status or photo — regardless of any Employee Number."""

    def __init__(self, db: Session, allowed, directory: DirectorySnapshot, site_id: str | None = None,
                 index: MappingIndex | None = None):
        self.available = directory.available
        self.site_id = site_id
        self.index = index or MappingIndex.load(db, allowed_site_ids=allowed, directory=directory)

    def resolve(self, code: str, day: date, site_id: str | None = None):
        return self.index.resolve(site_id or self.site_id, code, day)

    def describe(self, code: str, first: date | None = None, last: date | None = None,
                 site_id: str | None = None) -> dict:
        ref = last or first or date.today()
        r = self.resolve(code, ref, site_id)
        out = {"emp_code": code, "employee_name": None, "department": None, "employment_status": None,
               "has_photo": False, "identity_class": None, "zk_emp_code": code, "bamboohr_id": None,
               "employee_number": None, "mapping_status": r.mapping_status.value}
        if r.identified:
            out.update(identity_fields(r))
            out["zk_emp_code"] = code
            out["identity_class"] = legacy_identity_class(r, first or ref, ref)
        out.pop("zk_emp_codes", None)
        return out


def _search_hit(row: dict, q: str | None) -> bool:
    """Viewer search: employee name, BHR Employee ID or BambooHR Employee
    Number. ZKBioTime ID search is administrative (Identity Management)."""
    if not q:
        return True
    q = q.strip().lower()
    return any(q in (row.get(k) or "").lower() for k in ("employee_name", "bamboohr_id", "employee_number"))


def _has_code(row: dict, emp_code: str) -> bool:
    return emp_code in (row.get("zk_emp_codes") or [row["emp_code"]])


def _match(row: dict, *, q: str | None = None, emp_code: str | None = None, department: str | None = None,
           identity_class: str | None = None, employment_status: str | None = None,
           bamboohr_id: str | None = None) -> bool:
    """Shared row filter. ``emp_code`` selects the verified employee row that
    owns that ZKBioTime ID (exact string); ``q`` is a display-only search."""
    return (_search_hit(row, q)
            and (not emp_code or _has_code(row, emp_code))
            and (not bamboohr_id or row.get("bamboohr_id") == bamboohr_id)
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



def operational(db: Session, allowed, site_id: str, start: date, end: date, index: MappingIndex) -> dict:
    """Ingestion & identity coverage — operational monitoring, kept separate from
    identified attendance. Counts only (no names); shown to HEALTH/IDENTITY readers."""
    codes: set[str] = set()
    unmapped: set[str] = set()
    total = unmapped_punches = 0
    for code, d, n, _last in AttendanceRepository(db).code_day_stats(allowed_site_ids=allowed, site_id=site_id,
                                                                     date_from=start, date_to=end):
        codes.add(code)
        total += n
        if not index.resolve(site_id, code, d).identified:
            unmapped.add(code)
            unmapped_punches += n
    return {"active_codes": len(codes), "total_punches": total, "unmapped_codes": len(unmapped),
            "unmapped_punches": unmapped_punches}


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
             date_to: date | None = None, *, include_operational: bool = False) -> dict:
    """KPIs for one site-local day, or an inclusive range (``day``..``date_to``).
    Employee KPIs count distinct VERIFIED BambooHR employees (never codes);
    ``review_breakdown`` counts employee-days per flag. Unmapped attendance is
    excluded here and reported only in the operational block."""
    ident = Identity(db, allowed, directory, site_id)
    end = date_to or day
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=day, date_to=end, directory=directory, index=ident.index)
    breakdown = Counter(f for r in rows for f in r["flags"])

    def flagged(flag: str) -> int:
        return len({r["bamboohr_id"] for r in rows if flag in r["flags"]})

    fresh = freshness(db, allowed_site_ids=(site_id,))
    site_fresh = fresh["sites"][0] if fresh["sites"] else {}
    identified = len({r["bamboohr_id"] for r in rows})
    out = {
        "site_id": site_id, "date": day.isoformat(), "date_from": day.isoformat(), "date_to": end.isoformat(),
        "time_zone": tz,
        "directory_available": ident.available,
        "kpis": {
            "employees_with_activity": identified,
            "total_events": sum(r["punch_count"] for r in rows),
            "activity_days": len({r["local_date"] for r in rows}),
            "employees_needing_review": len({r["bamboohr_id"] for r in rows if r["flags"]}),
            "single_punch_employees": flagged(ReviewFlag.SINGLE_PUNCH.value),
            # Legacy key: identified rows are never unmatched (unmapped codes live in Identity Management).
            "unmatched_codes": 0,
            "feed_state": site_fresh.get("feed_state"),
            "identified_employees": identified,
            "identified_punches": sum(r["punch_count"] for r in rows),
        },
        "review_breakdown": {f: breakdown.get(f, 0) for f in REVIEW_FLAGS},
        "last_successful_sync_at": fresh["last_successful_sync_at"],
        "latest_received_utc": site_fresh.get("latest_received_utc"),
        "agent_heartbeat_utc": site_fresh.get("agent_heartbeat_utc"),
    }
    if include_operational:
        out["operational"] = operational(db, allowed, site_id, day, end, ident.index)
    return out


def hourly(db: Session, allowed, site_id: str, day: date, date_to: date | None = None,
           directory: DirectorySnapshot | None = None) -> dict:
    """Identified events and distinct verified employees per site-local hour."""
    end = date_to or day
    index = MappingIndex.load(db, allowed_site_ids=allowed, directory=directory or DirectorySnapshot(False))
    events: Counter = Counter()
    people: dict[str, set[str]] = defaultdict(set)
    for hh, code, d, n in AttendanceRepository(db).code_day_hours(
            allowed_site_ids=allowed, site_id=site_id, date_from=day, date_to=end,
            code_windows=index.windows(site_id, day, end)):
        r = index.resolve(site_id, code, d)
        if r.identified:
            events[hh] += n
            people[hh].add(r.bamboohr_id)
    return {
        "site_id": site_id, "date": day.isoformat(), "date_from": day.isoformat(), "date_to": end.isoformat(),
        "hours": [{"hour": h, "events": events.get(f"{h:02d}", 0), "employees": len(people.get(f"{h:02d}", ()))}
                  for h in range(24)],
    }


def trend(db: Session, allowed, site_id: str, start: date, end: date,
          directory: DirectorySnapshot | None = None) -> dict:
    index = MappingIndex.load(db, allowed_site_ids=allowed, directory=directory or DirectorySnapshot(False))
    events: Counter = Counter()
    people: dict[date, set[str]] = defaultdict(set)
    for code, d, n, _last in AttendanceRepository(db).code_day_stats(
            allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
            code_windows=index.windows(site_id, start, end)):
        r = index.resolve(site_id, code, d)
        if r.identified:
            events[d] += n
            people[d].add(r.bamboohr_id)
    days = []
    d = start
    while d <= end:
        days.append({"date": d.isoformat(), "events": events.get(d, 0), "employees": len(people.get(d, ()))})
        d += timedelta(days=1)
    return {"site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(), "days": days}


def _event_out(e: AttendanceEvent, ident: Identity, *, technical: bool) -> dict:
    out = {
        **ident.describe(e.emp_code, e.site_local_date, e.site_local_date, site_id=e.site_id),
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



def _employee_filter(index: MappingIndex, site_id: str, start: date, end: date, *, q: str | None,
                     department: str | None, emp_code: str | None, bamboohr_id: str | None) -> set[str] | None:
    """Verified employees selected by the viewer filters (None = no restriction).
    ``emp_code`` selects the employee(s) that verifiably owned that ID in the period."""
    if not (q or department or emp_code or bamboohr_id):
        return None
    chosen = set(index.employees_in_period(site_id, start, end))
    if emp_code:
        chosen &= {p.bamboohr_id for p in index.periods_for_code(site_id, emp_code) if p.clip(start, end)}
    if bamboohr_id:
        chosen &= {bamboohr_id}
    if q or department:
        keep = set()
        for bid in chosen:
            e = index.employee(bid) or {}
            row = {"employee_name": e.get("display_name"), "bamboohr_id": bid,
                   "employee_number": e.get("employee_number"), "department": e.get("department")}
            if _search_hit(row, q) and (not department or (row["department"] or "") == department):
                keep.add(bid)
        chosen = keep
    return chosen


def select_activity(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot, *,
                    q: str | None, department: str | None, terminal: str | None, identity_class: str | None,
                    flag: str | None, tz: str | None, emp_code: str | None = None, offset: int = 0,
                    limit: int = 50, hour: int | None = None, oldest_first: bool = False,
                    bamboohr_id: str | None = None, index: MappingIndex | None = None,
                    ) -> tuple[int, list[AttendanceEvent]]:
    """The single Activity selection shared by the paged UI and the Excel
    export (newest first). Only events inside verified mapping periods are
    selectable; identity class and review flags are evaluated per verified
    employee-day — the same values each row displays."""
    repo = AttendanceRepository(db)
    index = index or MappingIndex.load(db, allowed_site_ids=allowed, directory=directory)
    employees = _employee_filter(index, site_id, start, end, q=q, department=department, emp_code=emp_code,
                                 bamboohr_id=bamboohr_id)
    windows = index.windows(site_id, start, end, bamboohr_ids=employees)
    tz_only = flag == ReviewFlag.TZ_INCONSISTENT.value
    day_flag = flag if flag and not tz_only else None
    utc = hour_windows(start, end, hour, tz) if hour is not None else None
    if identity_class or day_flag:
        rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz, date_from=start,
                              date_to=end, directory=directory, bamboohr_ids=employees, index=index)
        selected = [r for r in rows if (not identity_class or r["identity_class"] == identity_class)
                    and (not day_flag or day_flag in r["flags"])]
        windows = [(c, date.fromisoformat(r["local_date"]), date.fromisoformat(r["local_date"]))
                   for r in selected for c in r["zk_emp_codes"]]
    return repo.events_page(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
                            terminal=terminal, tz_inconsistent_only=tz_only, offset=offset, limit=limit,
                            utc_windows=utc, oldest_first=oldest_first, code_windows=windows)


def activity(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot, *,
             q: str | None, department: str | None, terminal: str | None, identity_class: str | None,
             flag: str | None, page: int, page_size: int, technical: bool, tz: str | None = None,
             emp_code: str | None = None, hour: int | None = None, oldest_first: bool = False,
             bamboohr_id: str | None = None) -> dict:
    ident = Identity(db, allowed, directory, site_id)
    total, rows = select_activity(db, allowed, site_id, start, end, directory, q=q, department=department,
                                  terminal=terminal, identity_class=identity_class, flag=flag, tz=tz,
                                  emp_code=emp_code, offset=(page - 1) * page_size, limit=page_size,
                                  hour=hour, oldest_first=oldest_first, bamboohr_id=bamboohr_id, index=ident.index)
    items = [_event_out(e, ident, technical=technical) for e in rows]
    # Review flags of each row's verified employee-day — computed for this page's rows only.
    if rows:
        days = {(r["local_date"], r["bamboohr_id"]): r["flags"] for r in daily_activity(
            db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
            date_from=min(e.site_local_date for e in rows), date_to=max(e.site_local_date for e in rows),
            directory=directory, bamboohr_ids={i["bamboohr_id"] for i in items if i["bamboohr_id"]},
            index=ident.index)}
        for item in items:
            item["review_flags"] = days.get((item["local_date"], item["bamboohr_id"]), [])
    return {"total": total, "page": page, "page_size": page_size, "directory_available": ident.available,
            "items": items}


def _with_terminals(db, allowed, site_id, start, end, rows: list[dict], emp_codes=None) -> list[dict]:
    terms: dict[tuple[str, str], set[str]] = defaultdict(set)
    codes = {c for r in rows for c in (r.get("zk_emp_codes") or [r["emp_code"]])} if emp_codes is not None else None
    for d, code, t in AttendanceRepository(db).terminals_by_day(
        allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end, emp_codes=codes,
    ):
        if t:
            terms[(d.isoformat(), code)].add(t)
    for r in rows:
        names: set[str] = set()
        for c in r.get("zk_emp_codes") or [r["emp_code"]]:
            names |= terms.get((r["local_date"], c), set())
        r["terminal_names"] = sorted(names)
    return rows


def today_view(db: Session, allowed, site_id: str, tz: str | None, day: date, directory: DirectorySnapshot, *,
               q: str | None, department: str | None, review: str | None, sort: str, page: int, page_size: int,
               emp_code: str | None = None, identity_class: str | None = None, bamboohr_id: str | None = None) -> dict:
    ident = Identity(db, allowed, directory, site_id)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=day, date_to=day, directory=directory, index=ident.index)
    departments = sorted({r["department"] for r in rows if r.get("department")})
    rows = [r for r in rows if _match(r, q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                                      bamboohr_id=bamboohr_id) and _review_hit(r, review)]
    key, reverse = (sort.lstrip("-"), sort.startswith("-"))
    sort_keys = {
        "first_activity": lambda r: r["first_activity_utc"], "latest_activity": lambda r: r["latest_activity_utc"],
        "punch_count": lambda r: r["punch_count"], "span": lambda r: r["span_minutes"],
        "employee": lambda r: (r.get("employee_name") or "~", r["emp_code"]), "flags": lambda r: len(r["flags"]),
    }
    rows.sort(key=sort_keys.get(key, sort_keys["first_activity"]), reverse=reverse)
    paged = _page(rows, page, page_size)
    _with_terminals(db, allowed, site_id, day, day, paged["items"], True)
    return {**paged, "site_id": site_id, "date": day.isoformat(), "departments": departments,
            "directory_available": ident.available}


def employees(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date, directory: DirectorySnapshot,
              *, q: str | None, department: str | None, status_filter: str | None, activity_filter: str | None,
              page: int, page_size: int, emp_code: str | None = None, identity_class: str | None = None,
              sort: str = "-events", bamboohr_id: str | None = None) -> dict:
    """One row per VERIFIED BambooHR employee with a mapping in the period
    (several ZKBioTime IDs -> one row). Events, days and last activity count
    only punches inside that employee's verified periods. Directory entries
    without a verified mapping and unmapped codes are not listed."""
    ident = Identity(db, allowed, directory, site_id)
    index = ident.index
    repo = AttendanceRepository(db)
    in_period = index.employees_in_period(site_id, start, end)
    events: Counter = Counter()
    act_days: dict[str, set[date]] = defaultdict(set)
    for code, d, n, _last in repo.code_day_stats(allowed_site_ids=allowed, site_id=site_id, date_from=start,
                                                 date_to=end, code_windows=index.windows(site_id, start, end)):
        r = index.resolve(site_id, code, d)
        if r.identified:
            events[r.bamboohr_id] += n
            act_days[r.bamboohr_id].add(d)
    last_ever: dict[str, object] = {}
    for code, d, _n, last in repo.code_day_stats(allowed_site_ids=allowed, site_id=site_id,
                                                 code_windows=index.windows(site_id, date.min, date.max)):
        r = index.resolve(site_id, code, d)
        if r.identified and (r.bamboohr_id not in last_ever or last > last_ever[r.bamboohr_id]):
            last_ever[r.bamboohr_id] = last
    flags: Counter = Counter()
    for r in daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                            date_from=start, date_to=end, directory=directory, index=index):
        flags[r["bamboohr_id"]] += len(r["flags"])

    out = []
    for bid, periods in in_period.items():
        latest = max(periods, key=lambda p: (p.valid_to or date.max, p.valid_from))
        ref = min(end, latest.valid_to) if latest.valid_to else end
        r = index.resolve(site_id, latest.zk_emp_code, ref)
        if not r.identified:
            continue
        first_cov = max(start, min(p.valid_from for p in periods))
        row = {"emp_code": latest.zk_emp_code, **identity_fields(r, {p.zk_emp_code for p in periods}),
               "in_directory": True,
               "events": events.get(bid, 0), "activity_days": len(act_days.get(bid, ())),
               "review_flags": flags.get(bid, 0),
               "last_activity_local": to_site_local(last_ever.get(bid), tz),
               "identity_class": legacy_identity_class(r, first_cov, ref)}
        out.append(row)
    departments = sorted({r["department"] for r in out if r.get("department")})
    out = [r for r in out if _match(r, q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                                    employment_status=status_filter, bamboohr_id=bamboohr_id)]
    summary = {  # the filtered population for the period, before the activity filter
        "employees": len(out),
        "with_activity": sum(1 for r in out if r["events"]),
        "active": sum(1 for r in out if (r.get("employment_status") or "").lower() == "active"),
        "inactive": sum(1 for r in out if (r.get("employment_status") or "").lower() == "inactive"),
        "not_in_directory": sum(1 for r in out if r["mapping_status"] == MappingStatus.MAPPED_DIRECTORY_MISSING),
        "needing_review": sum(1 for r in out if r["review_flags"]),
        "matched": len(out),
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


def employee_for_code(db: Session, allowed, site_id: str, code: str, start: date, end: date,
                      directory: DirectorySnapshot) -> str | None:
    """LEGACY addressing: the verified employee who owned ``code`` in the period
    (the most recent owner when the ID was reassigned); None if unverified."""
    periods = [p for p in MappingIndex.load(db, allowed_site_ids=allowed, directory=directory)
               .periods_for_code(site_id, code) if p.clip(start, end)]
    if not periods:
        return None
    return max(periods, key=lambda p: (p.valid_to or date.max, p.valid_from)).bamboohr_id


def employee_detail(db: Session, allowed, site_id: str, tz: str | None, bamboohr_id: str, start: date, end: date,
                    directory: DirectorySnapshot, *, technical: bool, include_events: bool = True) -> dict:
    """Profile and attendance of one VERIFIED BambooHR employee: every ZKBioTime
    ID mapped to them, each only inside its verified period."""
    ident = Identity(db, allowed, directory, site_id)
    index = ident.index
    profile_r = index.describe_employee(bamboohr_id, site_id)
    if profile_r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    repo = AttendanceRepository(db)
    days = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=start, date_to=end, directory=directory, bamboohr_ids={bamboohr_id}, index=index)
    _with_terminals(db, allowed, site_id, start, end, days, True)
    windows = index.windows(site_id, start, end, bamboohr_ids={bamboohr_id})
    # Raw events are optional: the profile loads them per selected day via
    # /activity (paged) instead of downloading the whole period up front.
    events = repo.events_page(allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
                              code_windows=windows, offset=0, limit=2000)[1] if include_events else []
    periods = index.periods_for_employee(bamboohr_id, site_id)
    in_period = [p for p in periods if p.clip(start, end)]
    first = max(start, min((p.valid_from for p in in_period), default=start))
    profile = {"emp_code": profile_r.emp_code, **identity_fields(profile_r, {p.zk_emp_code for p in in_period}
                                                                 or {profile_r.emp_code}),
               "identity_class": legacy_identity_class(profile_r, first, end),
               "job_title": profile_r.job_title, "match_count": 1}
    return {
        "site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(),
        "profile": profile,
        "mappings": [{"mapping_id": p.id, "zk_emp_code": p.zk_emp_code, "valid_from": p.valid_from.isoformat(),
                      "valid_to": p.valid_to.isoformat() if p.valid_to else None} for p in periods],
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
    ReviewFlag.UNMATCHED_CODE.value: "The ZKBioTime ID has no verified BambooHR mapping for this day.",
    ReviewFlag.AMBIGUOUS_CODE.value: "More than one verified mapping covers this ZKBioTime ID on this day.",
    ReviewFlag.INACTIVE_EMPLOYEE_ACTIVITY.value: (
        "Activity is recorded for an employee who is inactive or past their termination date."
    ),
    ReviewFlag.BEFORE_HIRE_ACTIVITY.value: "Activity is recorded before the employee's hire date.",
    ReviewFlag.TZ_INCONSISTENT.value: "The source local time does not match the site's configured time zone.",
}



def exceptions(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date, directory: DirectorySnapshot,
               *, flag: str | None, q: str | None, page: int, page_size: int, emp_code: str | None = None,
               department: str | None = None, identity_class: str | None = None, sort: str = "-date",
               bamboohr_id: str | None = None) -> dict:
    ident = Identity(db, allowed, directory, site_id)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=start, date_to=end, directory=directory, index=ident.index)
    counts = Counter(f for r in rows for f in r["flags"])
    items = []
    for r in rows:
        if not r["flags"] or (flag and flag not in r["flags"]):
            continue
        item = {**r, "reasons": [{"flag": f, "reason": _FLAG_REASON[f]} for f in r["flags"]]}
        if _match(item, q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                  bamboohr_id=bamboohr_id):
            items.append(item)
    items.sort(key=lambda r: (r["local_date"], r["first_activity_utc"]), reverse=True)
    _sort_rows(items, sort, EXCEPTION_SORTS)
    paged = _page(items, page, page_size)
    _with_terminals(db, allowed, site_id, start, end, paged["items"], True)
    return {**paged, "site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(),
            "counts": {f: counts.get(f, 0) for f in REVIEW_FLAGS}, "directory_available": ident.available}


IDENTITY_CLASSES = [c.value for c in IdentityClass]
MAPPING_STATUSES = [c.value for c in MappingStatus]
