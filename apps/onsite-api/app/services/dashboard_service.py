"""Diji On-site Dashboard V1 — server-side assembly of the operational views.

Neutral facts only (first/latest activity, punch count, span, terminals,
needs-review flags). No Present/Absent/Late/Early/worked-hours judgements —
those need an approved attendance policy. ``PunchState`` is passed through
raw and never interpreted. Employee identity comes ONLY from administrator-
verified ZKBioTime ID -> BambooHR mappings (``identity_resolution``).
Employee-attributed views (Today, Team Members, Exceptions, attributed KPIs,
attendance exports) contain verified attendance only. Activity (with a
``mapping`` filter) and the Overview charts show ALL recorded events, each
classified VERIFIED / UNMAPPED / CONFLICT for its own site-local day; an
unverified event shows its raw ZKBioTime ID and never a person. Headcounts
count distinct BambooHR employees, never codes.
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
from app.services import attendance_review_service as reviews
from app.services.attendance_summary import daily_activity, daily_identity_rows, identity_fields, recorded_span
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


# --- mapping states (Activity + Overview charts) -------------------------------
# Every recorded event is in exactly one state for ITS OWN site-local day:
#   VERIFIED  — one verified mapping covers that day (attributed to that person)
#   UNMAPPED  — no verified mapping covers that day
#   CONFLICT  — more than one mapping covers that day (never attributed)
# "Needs review" (filter value ``unverified``) = UNMAPPED + CONFLICT.
VERIFIED, UNMAPPED, CONFLICT = "VERIFIED", "UNMAPPED", "CONFLICT"
MAPPING_FILTERS = ("all", "verified", "unverified", "conflict")
STATES = (VERIFIED, UNMAPPED, CONFLICT)


def mapping_state(r) -> str:
    if r.identified:
        return VERIFIED
    return CONFLICT if r.mapping_status == MappingStatus.MAPPING_CONFLICT else UNMAPPED


def _subtract(windows: list[tuple[str, date, date]], holes: list[tuple[str, date, date]]) -> list[tuple[str, date, date]]:
    """``windows`` minus ``holes`` (same code), as inclusive day windows."""
    by_code: dict[str, list[tuple[date, date]]] = defaultdict(list)
    for c, lo, hi in holes:
        by_code[c].append((lo, hi))
    out = []
    for c, lo, hi in windows:
        pieces = [(lo, hi)]
        for hlo, hhi in by_code.get(c, ()):
            nxt = []
            for plo, phi in pieces:
                if hhi < plo or hlo > phi:
                    nxt.append((plo, phi))
                    continue
                if plo < hlo:
                    nxt.append((plo, hlo - timedelta(days=1)))
                if hhi < phi:
                    nxt.append((hhi + timedelta(days=1), phi))
            pieces = nxt
        out.extend((c, a, b) for a, b in pieces)
    return out


def _search_hit(row: dict, q: str | None) -> bool:
    """Viewer search: employee name, BHR ID or BambooHR Employee
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
            # All recorded events by mapping state (same totals as the charts and Activity "All").
            **recorded_split(db, allowed, site_id, day, end, ident.index),
        },
        "review_breakdown": {f: breakdown.get(f, 0) for f in REVIEW_FLAGS},
        "last_successful_sync_at": fresh["last_successful_sync_at"],
        "latest_received_utc": site_fresh.get("latest_received_utc"),
        "agent_heartbeat_utc": site_fresh.get("agent_heartbeat_utc"),
    }
    # Earliest / Latest Recorded Fingerprint — single site-local day only.
    out["extremes"] = extremes(db, allowed, site_id, tz, day, ident) if day == end else None
    if include_operational:
        out["operational"] = operational(db, allowed, site_id, day, end, ident.index)
    return out


def extremes(db: Session, allowed, site_id: str, tz: str | None, day: date, ident: Identity) -> dict:
    """The earliest and latest recorded fingerprint of one site-local day over
    ALL recorded events (every mapping state), with every tie. Recorded at an
    entry-side reader: never a confirmed arrival, exit or presence. An
    unverified fingerprint carries only its raw ZKBioTime ID."""
    lo, hi = AttendanceRepository(db).day_extremes(allowed_site_ids=allowed, site_id=site_id, day=day)

    def entry(e: AttendanceEvent) -> dict:
        r = ident.resolve(e.emp_code, e.site_local_date, site_id)
        state = mapping_state(r)
        verified = state == VERIFIED
        return {"zk_emp_code": e.emp_code, "mapping_state": state, "local_time": e.punch_time_local,
                "bamboohr_id": r.bamboohr_id if verified else None,
                "employee_name": r.employee_name if verified else None,
                "employee_number": r.employee_number if verified else None, "terminal": e.terminal_alias}

    def block(events: list[AttendanceEvent]) -> dict | None:
        if not events:
            return None
        entries = [entry(e) for e in events]
        return {"local_time": events[0].punch_time_local, "punch_time_utc": events[0].punch_time_utc.isoformat(),
                "tied": len(entries), "entries": entries}

    return {"date": day.isoformat(), "time_zone": tz, "earliest": block(lo), "latest": block(hi)}


def _state_counts(counter: dict, key) -> dict:
    return {"verified_events": counter[VERIFIED].get(key, 0), "unmapped_events": counter[UNMAPPED].get(key, 0),
            "conflict_events": counter[CONFLICT].get(key, 0)}


def day_groups(index: MappingIndex, site_id: str, bounds) -> dict:
    """Whole site-local days per identity: a verified person (all of their
    ZKBioTime IDs that day) or, when unverified, the raw ZKBioTime ID.
    ``bounds`` = (code, date, events, first_local, last_local) per code-day.
    Returns {(state, identity, date): [events, first_local, last_local]}."""
    groups: dict[tuple, list] = {}
    for code, d, n, first, last in bounds:
        r = index.resolve(site_id, code, d)
        state = mapping_state(r)
        key = (state, r.bamboohr_id if state == VERIFIED else code, d)
        g = groups.get(key)
        if g is None:
            groups[key] = [n, first, last]
        else:
            g[0] += n
            g[1] = min(g[1], first)
            g[2] = max(g[2], last)
    return groups


def hourly(db: Session, allowed, site_id: str, day: date, date_to: date | None = None,
           directory: DirectorySnapshot | None = None) -> dict:
    """ALL recorded events per site-local hour, split by mapping state (each
    event classified for its own day), plus distinct verified people and the
    hour of each identity's first / last recorded punch of the whole day
    (single = only one punch that day). Never interpreted as check-in/out."""
    end = date_to or day
    index = MappingIndex.load(db, allowed_site_ids=allowed, directory=directory or DirectorySnapshot(False))
    repo = AttendanceRepository(db)
    by_state: dict[str, Counter] = {s: Counter() for s in STATES}
    people: dict[str, set[str]] = defaultdict(set)
    for hh, code, d, n in repo.code_day_hours(allowed_site_ids=allowed, site_id=site_id, date_from=day, date_to=end):
        r = index.resolve(site_id, code, d)
        state = mapping_state(r)
        by_state[state][hh] += n
        if state == VERIFIED:
            people[hh].add(r.bamboohr_id)
    seq = {k: {s: Counter() for s in STATES} for k in ("first", "last", "single")}
    for (state, _ident, _d), (n, first, last) in day_groups(index, site_id, repo.code_day_bounds(
            allowed_site_ids=allowed, site_id=site_id, date_from=day, date_to=end)).items():
        if n == 1:
            seq["single"][state][first[11:13]] += 1
        else:
            seq["first"][state][first[11:13]] += 1
            seq["last"][state][last[11:13]] += 1
    hours = []
    for h in range(24):
        hh = f"{h:02d}"
        split = _state_counts(by_state, hh)
        hours.append({"hour": h, "events": sum(split.values()), "employees": len(people.get(hh, ())), **split,
                      **{k: {s.lower(): seq[k][s].get(hh, 0) for s in STATES} for k in seq}})
    return {"site_id": site_id, "date": day.isoformat(), "date_from": day.isoformat(), "date_to": end.isoformat(),
            "hours": hours}


def trend(db: Session, allowed, site_id: str, start: date, end: date,
          directory: DirectorySnapshot | None = None) -> dict:
    """ALL recorded events per site-local day, split by mapping state, plus
    distinct verified people."""
    index = MappingIndex.load(db, allowed_site_ids=allowed, directory=directory or DirectorySnapshot(False))
    by_state: dict[str, Counter] = {s: Counter() for s in STATES}
    people: dict[date, set[str]] = defaultdict(set)
    for code, d, n, _last in AttendanceRepository(db).code_day_stats(
            allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end):
        r = index.resolve(site_id, code, d)
        state = mapping_state(r)
        by_state[state][d] += n
        if state == VERIFIED:
            people[d].add(r.bamboohr_id)
    days = []
    d = start
    while d <= end:
        split = _state_counts(by_state, d)
        days.append({"date": d.isoformat(), "events": sum(split.values()), "employees": len(people.get(d, ())),
                     **split})
        d += timedelta(days=1)
    return {"site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(), "days": days}


def recorded_split(db: Session, allowed, site_id: str, start: date, end: date, index: MappingIndex) -> dict:
    """Recorded events in the range by mapping state (Overview KPIs)."""
    out = {VERIFIED: 0, UNMAPPED: 0, CONFLICT: 0}
    for code, d, n, _last in AttendanceRepository(db).code_day_stats(allowed_site_ids=allowed, site_id=site_id,
                                                                     date_from=start, date_to=end):
        out[mapping_state(index.resolve(site_id, code, d))] += n
    return {"recorded_events": sum(out.values()), "verified_events": out[VERIFIED],
            "unmapped_events": out[UNMAPPED], "conflict_events": out[CONFLICT]}


def _event_out(e: AttendanceEvent, ident: Identity, *, technical: bool) -> dict:
    described = ident.describe(e.emp_code, e.site_local_date, e.site_local_date, site_id=e.site_id)
    state = mapping_state(ident.resolve(e.emp_code, e.site_local_date, e.site_id))
    if state != VERIFIED:  # the raw ZKBioTime ID only: never a name, BHR ID, number or hint
        described["identity_class"] = (IdentityClass.AMBIGUOUS if state == CONFLICT
                                       else IdentityClass.UNMATCHED).value
    out = {
        **described,
        "mapping_state": state,
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


def _mapping_plan(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot,
                  index: MappingIndex, *, mapping: str, q: str | None, department: str | None,
                  terminal: str | None, identity_class: str | None, flag: str | None, tz: str | None,
                  emp_code: str | None, hour: int | None, bamboohr_id: str | None) -> dict | None:
    """Shared WHERE inputs of the mapping-aware Activity selection, so the page,
    its total, its state counts and the export are the same selection.

    * ``emp_code`` is the exact ZKBioTime ID (SQL), in every state.
    * Name/BHR ID/EMP Number search, department and BHR ID can only match
      verified events, as do the legacy identity classes and day review flags.
    Returns None when nothing can match."""
    tz_only = flag == ReviewFlag.TZ_INCONSISTENT.value
    day_flag = flag if flag and not tz_only else None
    conflicts = index.conflict_windows(site_id, start, end)
    verified = _subtract(index.windows(site_id, start, end), conflicts)
    restrict = None  # verified-only restriction from person filters
    employees = _employee_filter(index, site_id, start, end, q=q, department=department, emp_code=None,
                                 bamboohr_id=bamboohr_id)
    if employees is not None:
        restrict = _subtract(index.windows(site_id, start, end, bamboohr_ids=employees), conflicts)
    if identity_class or day_flag:
        rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz, date_from=start,
                              date_to=end, directory=directory, bamboohr_ids=employees, index=index)
        selected = [r for r in rows if (not identity_class or r["identity_class"] == identity_class)
                    and (not day_flag or day_flag in r["flags"])]
        restrict = _subtract([(c, date.fromisoformat(r["local_date"]), date.fromisoformat(r["local_date"]))
                              for r in selected for c in r["zk_emp_codes"]], conflicts)
    base = {"date_from": start, "date_to": end, "terminal": terminal, "tz_inconsistent_only": tz_only,
            "utc_windows": hour_windows(start, end, hour, tz) if hour is not None else None,
            "emp_codes": [emp_code] if emp_code else None}
    if mapping == "all":
        select_kw = {"code_windows": restrict}
    elif mapping == "verified":
        select_kw = {"code_windows": restrict if restrict is not None else verified}
    elif mapping == "conflict":
        if restrict is not None:
            return None
        select_kw = {"code_windows": conflicts}
    else:  # unverified = unmapped + conflict = NOT verified
        if restrict is not None:
            return None
        select_kw = {"exclude_code_windows": verified}
    return {"base": base, "select": select_kw, "restrict": restrict, "verified": verified, "conflicts": conflicts}


def activity_counts(db: Session, allowed, site_id: str, plan: dict | None) -> dict:
    """Recorded / verified / unmapped / conflict for the filters (ignoring the
    mapping filter itself), from one aggregate query."""
    if plan is None:
        return {"recorded": 0, "verified": 0, "unverified": 0, "unmapped": 0, "conflict": 0}
    c = AttendanceRepository(db).mapping_counts(
        allowed_site_ids=allowed, site_id=site_id, verified_windows=plan["verified"],
        conflict_windows=plan["conflicts"], code_windows=plan["restrict"], **plan["base"])
    return {**c, "unverified": c["unmapped"] + c["conflict"]}


def select_activity(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot, *,
                    q: str | None, department: str | None, terminal: str | None, identity_class: str | None,
                    flag: str | None, tz: str | None, emp_code: str | None = None, offset: int = 0,
                    limit: int = 50, hour: int | None = None, oldest_first: bool = False,
                    bamboohr_id: str | None = None, index: MappingIndex | None = None,
                    mapping: str | None = None,
                    ) -> tuple[int, list[AttendanceEvent]]:
    """The single Activity selection shared by the paged UI and the Excel
    export (newest first).

    ``mapping=None`` is the verified employee-attributed selection (exports,
    recent activity, profiles — unchanged). ``mapping`` = all | verified |
    unverified | conflict selects recorded events by the mapping state of
    their own day (see ``_mapping_plan``)."""
    repo = AttendanceRepository(db)
    index = index or MappingIndex.load(db, allowed_site_ids=allowed, directory=directory)
    if mapping is not None:
        plan = _mapping_plan(db, allowed, site_id, start, end, directory, index, mapping=mapping, q=q,
                             department=department, terminal=terminal, identity_class=identity_class, flag=flag,
                             tz=tz, emp_code=emp_code, hour=hour, bamboohr_id=bamboohr_id)
        if plan is None:
            return 0, []
        return repo.events_page(allowed_site_ids=allowed, site_id=site_id, offset=offset, limit=limit,
                                oldest_first=oldest_first, **plan["base"], **plan["select"])
    employees = _employee_filter(index, site_id, start, end, q=q, department=department, emp_code=emp_code,
                                 bamboohr_id=bamboohr_id)
    # Conflict days (overlapping periods) are never attributed to anyone.
    windows = _subtract(index.windows(site_id, start, end, bamboohr_ids=employees),
                        index.conflict_windows(site_id, start, end))
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


FIRST, LAST, INTERMEDIATE, SINGLE = "FIRST", "LAST", "INTERMEDIATE", "SINGLE"


def _identity_key(index: MappingIndex, site_id: str, code: str, d: date) -> tuple:
    """The identity a punch belongs to on its own day: a verified person (all of
    their IDs that day) or the raw ZKBioTime ID (unmapped / conflict)."""
    r = index.resolve(site_id, code, d)
    return ("P", r.bamboohr_id, d) if r.identified else ("C", code, d)


def punch_sequences(db: Session, allowed, site_id: str, index: MappingIndex,
                    events: list[AttendanceEvent]) -> dict[str, dict]:
    """FIRST / LAST / INTERMEDIATE / SINGLE of each event within its identity's
    COMPLETE site-local day (every punch of every ID of that person that day,
    regardless of the page or filters). Recorded order only — never check-in/out."""
    if not events:
        return {}
    keys = {e.event_id: _identity_key(index, site_id, e.emp_code, e.site_local_date) for e in events}
    code_days: set[tuple[str, date]] = set()
    for (kind, ident, d) in set(keys.values()):
        if kind == "C":
            code_days.add((ident, d))
        else:
            for p in index.periods_for_employee(ident, site_id):
                if p.covers(d):
                    code_days.add((p.zk_emp_code, d))
    ordered: dict[tuple, list[tuple[str, datetime, str]]] = defaultdict(list)
    wanted = set(keys.values())
    days = [d for _c, d in code_days]
    for code, d, utc, event_id, local in AttendanceRepository(db).day_punches(
            allowed_site_ids=allowed, site_id=site_id, codes={c for c, _d in code_days},
            date_from=min(days), date_to=max(days)):
        if (code, d) not in code_days:
            continue
        key = _identity_key(index, site_id, code, d)
        if key in wanted:
            ordered[key].append((event_id, utc, local))
    out = {}
    for event_id, key in keys.items():
        day = ordered.get(key) or []
        seq = [e for e, _u, _l in day] or [event_id]
        pos = seq.index(event_id) if event_id in seq else 0
        n = len(seq)
        kind = SINGLE if n == 1 else FIRST if pos == 0 else LAST if pos == n - 1 else INTERMEDIATE
        out[event_id] = {
            "punch_sequence": kind, "punch_position": pos + 1, "punches_in_day": n,
            # Whole identity-day bounds (v0.9): recorded fingerprints, never entry/exit.
            "day_first_local": day[0][2] if day else None, "day_last_local": day[-1][2] if day else None,
            "day_span_minutes": recorded_span(day[0][1], day[-1][1], len(day)) if day else None,
        }
    return out


def activity(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot, *,
             q: str | None, department: str | None, terminal: str | None, identity_class: str | None,
             flag: str | None, page: int, page_size: int, technical: bool, tz: str | None = None,
             emp_code: str | None = None, hour: int | None = None, oldest_first: bool = False,
             bamboohr_id: str | None = None, mapping: str | None = None) -> dict:
    ident = Identity(db, allowed, directory, site_id)
    total, rows = select_activity(db, allowed, site_id, start, end, directory, q=q, department=department,
                                  terminal=terminal, identity_class=identity_class, flag=flag, tz=tz,
                                  emp_code=emp_code, offset=(page - 1) * page_size, limit=page_size,
                                  hour=hour, oldest_first=oldest_first, bamboohr_id=bamboohr_id, index=ident.index,
                                  mapping=mapping)
    items = [_event_out(e, ident, technical=technical) for e in rows]
    extra: dict = {}
    if mapping is not None:
        seqs = punch_sequences(db, allowed, site_id, ident.index, rows)
        for e, item in zip(rows, items, strict=True):
            item.update(seqs.get(e.event_id, {}))
        plan = _mapping_plan(db, allowed, site_id, start, end, directory, ident.index, mapping="all", q=q,
                             department=department, terminal=terminal, identity_class=identity_class, flag=flag,
                             tz=tz, emp_code=emp_code, hour=hour, bamboohr_id=bamboohr_id)
        extra = {"mapping": mapping, "summary": activity_counts(db, allowed, site_id, plan)}
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
            "items": items, **extra}


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
    """LEGACY addressing: the single verified employee who owned ``code`` during
    the period. FAILS CLOSED (None -> 404) when the ID is unverified in the
    period or was owned by more than one employee in it (reassigned/reused
    ID): the legacy route must never show the wrong person. The new contract
    addresses employees by BambooHR id instead."""
    owners = {p.bamboohr_id for p in MappingIndex.load(db, allowed_site_ids=allowed, directory=directory)
              .periods_for_code(site_id, code) if p.clip(start, end)}
    return owners.pop() if len(owners) == 1 else None


def employee_detail(db: Session, allowed, site_id: str, tz: str | None, bamboohr_id: str, start: date, end: date,
                    directory: DirectorySnapshot, *, technical: bool, include_events: bool = True) -> dict:
    """Profile and attendance of one VERIFIED BambooHR employee: every ZKBioTime
    ID mapped to them, each only inside its verified period."""
    ident = Identity(db, allowed, directory, site_id)
    index = ident.index
    profile_r = index.describe_employee(bamboohr_id, site_id)
    if profile_r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team member not found")
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
    ReviewFlag.SINGLE_PUNCH.value: (
        "Single Recorded Fingerprint: only one fingerprint was recorded on this completed day. "
        "An observation for optional review — not a violation."
    ),
    ReviewFlag.HIGH_PUNCH_COUNT.value: "An unusually high number of activities was recorded on this day.",
    ReviewFlag.POSSIBLE_DUPLICATE_TAP.value: "Two activities were recorded within 60 seconds of each other.",
    ReviewFlag.UNMATCHED_CODE.value: "The ZKBioTime ID has no verified BambooHR mapping for this day.",
    ReviewFlag.AMBIGUOUS_CODE.value: "More than one verified mapping covers this ZKBioTime ID on this day.",
    ReviewFlag.INACTIVE_EMPLOYEE_ACTIVITY.value: (
        "Activity is recorded for a team member who is inactive or past their termination date."
    ),
    ReviewFlag.BEFORE_HIRE_ACTIVITY.value: "Activity is recorded before the team member's hire date.",
    ReviewFlag.TZ_INCONSISTENT.value: "The source local time does not match the site's configured time zone.",
}



def exceptions(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date, directory: DirectorySnapshot,
               *, flag: str | None, q: str | None, page: int, page_size: int, emp_code: str | None = None,
               department: str | None = None, identity_class: str | None = None, sort: str = "-date",
               bamboohr_id: str | None = None, review_status: str | None = None) -> dict:
    ident = Identity(db, allowed, directory, site_id)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                          date_from=start, date_to=end, directory=directory, index=ident.index)
    counts = Counter(f for r in rows for f in r["flags"])
    items = []
    for r in rows:
        if not r["flags"] or (flag and flag not in r["flags"]):
            continue
        item = {**r, "identity_key": f"P:{r['bamboohr_id']}",
                "reasons": [{"flag": f, "reason": _FLAG_REASON[f]} for f in r["flags"]]}
        if _match(item, q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                  bamboohr_id=bamboohr_id):
            items.append(item)
    reviews.attach(db, allowed, site_id, tz, ident.index, items, start, end)
    items = [i for i in items if _review_status_hit(i, review_status)]
    items.sort(key=lambda r: (r["local_date"], r["first_activity_utc"]), reverse=True)
    _sort_rows(items, sort, EXCEPTION_SORTS)
    paged = _page(items, page, page_size)
    _with_terminals(db, allowed, site_id, start, end, paged["items"], True)
    return {**paged, "site_id": site_id, "date_from": start.isoformat(), "date_to": end.isoformat(),
            "counts": {f: counts.get(f, 0) for f in REVIEW_FLAGS}, "directory_available": ident.available}


DAILY_SORTS = {
    "date": lambda r: (r["local_date"], r["first_fingerprint_utc"]),
    "identity": lambda r: ((r.get("employee_name") or "~").lower(), r["emp_code"], r["local_date"]),
    "first": lambda r: (r["first_fingerprint_local"] or "")[11:],
    "last": lambda r: (r["last_fingerprint_local"] or "")[11:],
    "span": lambda r: (r["recorded_span_minutes"] is None, r["recorded_span_minutes"] or 0),
    "punches": lambda r: r["punch_count"],
}
REVIEW_STATUS_FILTERS = ("not_reviewed", "OPEN", "SUBMITTED", "RESOLVED", "REOPENED", "NEEDS_REASSESSMENT")


def _state_hit(row: dict, mapping: str) -> bool:
    s = row["mapping_state"]
    return (mapping == "all" or (mapping == "verified" and s == VERIFIED)
            or (mapping == "unverified" and s != VERIFIED) or (mapping == "conflict" and s == CONFLICT))


def _review_status_hit(row: dict, review_status: str | None) -> bool:
    rv = row.get("review")
    if not review_status:
        return True
    if review_status == "not_reviewed":
        return rv is None
    if review_status == "NEEDS_REASSESSMENT":
        return bool(rv and rv["stale"]) or any(c["stale"] for c in row.get("earlier_code_cases") or [])
    return bool(rv and rv["status"] == review_status)


def daily_rows(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date,
               directory: DirectorySnapshot, *, mapping: str = "all", q: str | None = None,
               emp_code: str | None = None, bamboohr_id: str | None = None, terminal: str | None = None,
               review_status: str | None = None, index: MappingIndex | None = None) -> tuple[list[dict], dict]:
    """Daily fingerprint activity for every identity, filtered — and the summary
    over the same filters WITHOUT the mapping filter (as on Activity), so the
    per-state totals are identical on every tab."""
    index = index or MappingIndex.load(db, allowed_site_ids=allowed, directory=directory)
    rows = daily_identity_rows(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz,
                               date_from=start, date_to=end, index=index)
    # Name / BHR ID / EMP Number search and BHR ID can only match verified rows;
    # the exact ZKBioTime ID matches in every state.
    base = [r for r in rows if _search_hit(r, q) and (not emp_code or emp_code in r["zk_emp_codes"])
            and (not bamboohr_id or r.get("bamboohr_id") == bamboohr_id)
            and (not terminal or terminal in r["terminal_names"])]
    reviews.attach(db, allowed, site_id, tz, index, base, start, end)
    base = [r for r in base if _review_status_hit(r, review_status)]
    summary = {"identity_days": len(base), "punches": sum(r["punch_count"] for r in base)}
    for s in STATES:
        part = [r for r in base if r["mapping_state"] == s]
        summary[f"{s.lower()}_identity_days"] = len(part)
        summary[f"{s.lower()}_punches"] = sum(r["punch_count"] for r in part)
    summary["single_fingerprint_days"] = sum(1 for r in base if r["single"])
    return [r for r in base if _state_hit(r, mapping)], summary


def daily_view(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date,
               directory: DirectorySnapshot, *, mapping: str, q: str | None, emp_code: str | None,
               bamboohr_id: str | None, terminal: str | None, review_status: str | None, sort: str, page: int,
               page_size: int) -> dict:
    rows, summary = daily_rows(db, allowed, site_id, tz, start, end, directory, mapping=mapping, q=q,
                               emp_code=emp_code, bamboohr_id=bamboohr_id, terminal=terminal,
                               review_status=review_status)
    rows.sort(key=DAILY_SORTS["date"], reverse=True)  # newest day first, stable tie-break
    _sort_rows(rows, sort, DAILY_SORTS)
    return {**_page(rows, page, page_size), "site_id": site_id, "date_from": start.isoformat(),
            "date_to": end.isoformat(), "time_zone": tz, "mapping": mapping, "summary": summary,
            "directory_available": directory.available}


IDENTITY_CLASSES = [c.value for c in IdentityClass]
MAPPING_STATUSES = [c.value for c in MappingStatus]
