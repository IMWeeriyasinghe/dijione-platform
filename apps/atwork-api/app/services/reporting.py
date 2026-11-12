"""Operational reports and exports. Not payroll: durations only, no pay rules."""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.utils import get_column_letter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.constants import STATUS_OPEN
from app.core.errors import AttendanceError
from app.models.attendance import AttendanceSession
from app.models.corrections import CorrectionRequest
from app.services.attendance_policy import AttendancePolicy
from app.services.employee_directory import display_name, employee_names
from app.services.time_accounting import Totals, daily_totals, is_unverified, local_day_bounds

MAX_RANGE_DAYS = 366


def checked_range(start: date, end: date) -> None:
    if start > end:
        raise AttendanceError("INVALID_DATE_RANGE", "The start date must not be after the end date.", 422)
    if (end - start).days >= MAX_RANGE_DAYS:
        raise AttendanceError("INVALID_DATE_RANGE", f"The date range must not exceed {MAX_RANGE_DAYS} days.", 422)


@dataclass(frozen=True)
class ReportFilter:
    date_from: date
    date_to: date
    user_id: int | None = None
    work_mode: str | None = None


def hours(seconds: int) -> float:
    return round(seconds / 3600, 2)


def _add(a: Totals, b: Totals) -> Totals:
    return Totals(
        a.gross_seconds + b.gross_seconds,
        a.break_seconds + b.break_seconds,
        a.provisional_seconds + b.provisional_seconds,
    )


class Reporting:
    def __init__(self, db: Session, policy: AttendancePolicy, now: datetime) -> None:
        self.db = db
        self.policy = policy
        self.now = now

    def sessions(self, flt: ReportFilter) -> list[AttendanceSession]:
        checked_range(flt.date_from, flt.date_to)
        zone = self.policy.zone
        start, end = local_day_bounds(flt.date_from, zone)[0], local_day_bounds(flt.date_to, zone)[1]
        stmt = select(AttendanceSession).where(
            AttendanceSession.check_in_at < end,
            or_(AttendanceSession.check_out_at.is_(None), AttendanceSession.check_out_at >= start),
        )
        if flt.user_id is not None:
            stmt = stmt.where(AttendanceSession.platform_user_id == flt.user_id)
        if flt.work_mode:
            stmt = stmt.where(AttendanceSession.work_mode == flt.work_mode)
        return list(self.db.scalars(stmt.order_by(AttendanceSession.check_in_at.desc())))

    def daily(self, sessions: list[AttendanceSession]) -> dict[date, Totals]:
        return daily_totals(sessions, self.policy.zone, self.now, self.policy.unverified_after_seconds)

    def unverified(self, session: AttendanceSession) -> bool:
        return is_unverified(session, self.now, self.policy.unverified_after_seconds)

    def in_range(self, session: AttendanceSession, flt: ReportFilter) -> Totals:
        """The part of one session inside the range, split at local midnight."""
        total = Totals()
        for day, value in self.daily([session]).items():
            if flt.date_from <= day <= flt.date_to:
                total = _add(total, value)
        return total

    def summary(self, flt: ReportFilter) -> dict:
        sessions = self.sessions(flt)
        names = employee_names(self.db, {s.platform_user_id for s in sessions})
        total, by_mode, by_user, by_day = Totals(), {}, {}, {}
        for session in sessions:
            part = self.in_range(session, flt)
            total = _add(total, part)
            by_mode[session.work_mode] = _add(by_mode.get(session.work_mode, Totals()), part)
            row = by_user.setdefault(session.platform_user_id, {"count": 0, "totals": Totals()})
            row["count"] += 1
            row["totals"] = _add(row["totals"], part)
            for day, value in self.daily([session]).items():
                if flt.date_from <= day <= flt.date_to:
                    by_day[day] = _add(by_day.get(day, Totals()), value)
        employees = sorted(
            (
                {
                    "platform_user_id": uid,
                    "employee_name": display_name(names, uid),
                    "session_count": r["count"],
                    "totals": r["totals"],
                }
                for uid, r in by_user.items()
            ),
            key=lambda r: r["employee_name"].lower(),
        )
        return {
            "session_count": len(sessions),
            "totals": total,
            "by_work_mode": by_mode,
            "by_employee": employees,
            "by_day": dict(sorted(by_day.items())),
        }

    def missed_checkouts(self, flt: ReportFilter | None = None) -> list[dict]:
        """Open sessions past the threshold. Flagged only: nothing is closed."""
        cutoff = self.now - timedelta(hours=self.policy.missed_checkout_hours)
        stmt = select(AttendanceSession).where(AttendanceSession.status == STATUS_OPEN, AttendanceSession.check_in_at <= cutoff)
        if flt is not None:
            checked_range(flt.date_from, flt.date_to)
            zone = self.policy.zone
            stmt = stmt.where(
                AttendanceSession.check_in_at >= local_day_bounds(flt.date_from, zone)[0],
                AttendanceSession.check_in_at < local_day_bounds(flt.date_to, zone)[1],
            )
            if flt.user_id is not None:
                stmt = stmt.where(AttendanceSession.platform_user_id == flt.user_id)
            if flt.work_mode:
                stmt = stmt.where(AttendanceSession.work_mode == flt.work_mode)
        sessions = list(self.db.scalars(stmt.order_by(AttendanceSession.check_in_at)))
        names = employee_names(self.db, {s.platform_user_id for s in sessions})
        return [
            {
                "session_id": s.id,
                "platform_user_id": s.platform_user_id,
                "employee_name": display_name(names, s.platform_user_id),
                "work_mode": s.work_mode,
                "check_in_at": s.check_in_at,
                "open_seconds": int((self.now - s.check_in_at).total_seconds()),
                "break_open": any(b.ended_at is None for b in s.breaks),
            }
            for s in sessions
        ]

    def corrections(self, flt: ReportFilter) -> list[CorrectionRequest]:
        checked_range(flt.date_from, flt.date_to)
        zone = self.policy.zone
        stmt = select(CorrectionRequest).where(
            CorrectionRequest.created_at >= local_day_bounds(flt.date_from, zone)[0],
            CorrectionRequest.created_at < local_day_bounds(flt.date_to, zone)[1],
        )
        if flt.user_id is not None:
            stmt = stmt.where(CorrectionRequest.platform_user_id == flt.user_id)
        return list(self.db.scalars(stmt.order_by(CorrectionRequest.created_at.desc())))

    def local(self, value: datetime | None) -> datetime | None:
        return value.astimezone(self.policy.zone) if value else None

    def work_date(self, value: datetime | str | None) -> date | None:
        """The business-time-zone date a session belongs to, from its check-in."""
        moment = datetime.fromisoformat(value) if isinstance(value, str) else value
        return moment.astimezone(self.policy.zone).date() if moment else None

    def local_iso(self, value: str | None) -> datetime | None:
        return self.local(datetime.fromisoformat(value)) if value else None

    def table(self, report: str, flt: ReportFilter) -> tuple[list[str], list[list]]:
        if report == "employee_summary":
            head = [
                "Employee",
                "User ID",
                "Sessions",
                "Gross hours",
                "Break hours",
                "Net hours",
                "Unverified hours (not included)",
            ]
            rows = [
                [
                    r["employee_name"],
                    r["platform_user_id"],
                    r["session_count"],
                    hours(r["totals"].gross_seconds),
                    hours(r["totals"].break_seconds),
                    hours(r["totals"].net_seconds),
                    hours(r["totals"].provisional_seconds),
                ]
                for r in self.summary(flt)["by_employee"]
            ]
            return head, rows
        if report == "sessions":
            sessions = self.sessions(flt)
            names = employee_names(self.db, {s.platform_user_id for s in sessions})
            head = [
                "Employee",
                "User ID",
                "Work mode",
                "Status",
                "Work date",
                "Check-in date/time",
                "Check-out date/time",
                "Gross hours in period",
                "Break hours in period",
                "Net hours in period",
                "Unverified",
                "Unverified hours in period (not included)",
                "Corrections",
            ]
            rows = []
            for s in sessions:
                part = self.in_range(s, flt)
                rows.append(
                    [
                        display_name(names, s.platform_user_id),
                        s.platform_user_id,
                        s.work_mode,
                        s.status,
                        self.work_date(s.check_in_at),
                        self.local(s.check_in_at),
                        self.local(s.check_out_at),
                        hours(part.gross_seconds),
                        hours(part.break_seconds),
                        hours(part.net_seconds),
                        "Yes" if self.unverified(s) else "No",
                        hours(part.provisional_seconds),
                        s.correction_count,
                    ]
                )
            return head, rows
        if report == "missed_checkouts":
            head = ["Employee", "User ID", "Work mode", "Work date", "Check-in date/time", "Open hours", "Break open"]
            rows = [
                [
                    r["employee_name"],
                    r["platform_user_id"],
                    r["work_mode"],
                    self.work_date(r["check_in_at"]),
                    self.local(r["check_in_at"]),
                    hours(r["open_seconds"]),
                    "Yes" if r["break_open"] else "No",
                ]
                for r in self.missed_checkouts(flt)
            ]
            return head, rows
        if report == "corrections":
            items = self.corrections(flt)
            names = employee_names(self.db, {i.platform_user_id for i in items})
            head = [
                "Employee",
                "User ID",
                "Type",
                "Status",
                "Affected work date",
                "Proposed check-in date/time",
                "Proposed check-out date/time",
                "Requested date/time",
                "Reviewer",
                "Reviewed date/time",
                "Reason",
                "Decision note",
            ]
            rows = [
                [
                    display_name(names, i.platform_user_id),
                    i.platform_user_id,
                    i.kind,
                    i.status,
                    self.work_date(i.proposed["check_in_at"]),
                    self.local_iso(i.proposed["check_in_at"]),
                    self.local_iso(i.proposed["check_out_at"]),
                    self.local(i.created_at),
                    i.reviewer_name or "",
                    self.local(i.reviewed_at),
                    i.reason,
                    i.decision_note or "",
                ]
                for i in items
            ]
            return head, rows
        raise AttendanceError("INVALID_REPORT", "Unknown report.", 422)


def safe_cell(value):
    """Spreadsheet programs run cells that start with these characters as formulas."""
    if (
        isinstance(value, str)
        and value.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@")
        or (isinstance(value, str) and value[:1] in ("\t", "\r"))
    ):
        return "'" + value
    return value


_REPORTS = {
    "sessions": ("Attendance Report", "Attendance"),
    "employee_summary": ("Employee Summary Report", "Employee_Summary"),
    "missed_checkouts": ("Missed Check-out Report", "Missed_Checkout"),
    "corrections": ("Correction Report", "Correction"),
}
_XLSX_DATE = "yyyy-mm-dd"
_XLSX_DATETIME = "yyyy-mm-dd hh:mm:ss"
_META_HEAD = ["Report", "Reporting period from", "Reporting period to", "Export generated at", "Time zone"]


@dataclass(frozen=True)
class ExportInfo:
    report: str
    period_from: date
    period_to: date
    generated_at: datetime  # aware, in the business time zone
    time_zone: str
    user_id: int | None = None
    work_mode: str | None = None

    @property
    def title(self) -> str:
        return _REPORTS[self.report][0]


def export_filename(info: ExportInfo, extension: str) -> str:
    """Built only from a fixed name and a timestamp, so it needs no escaping."""
    return f"DijiAtWork_{_REPORTS[info.report][1]}_Report_{info.generated_at:%Y-%m-%d_%H%M%S}.{extension}"


def _csv_value(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    return "" if value is None else safe_cell(value)


def to_csv(head: list[str], rows: list[list], info: ExportInfo) -> bytes:
    """Metadata sits in trailing columns so every line stays one plain record."""
    meta = [info.title, info.period_from.isoformat(), info.period_to.isoformat(), info.generated_at.isoformat(), info.time_zone]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(head + _META_HEAD)
    writer.writerows([_csv_value(v) for v in row] + meta for row in rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _xlsx_cell(sheet, row: int, column: int, value) -> None:
    if isinstance(value, datetime):
        sheet.cell(row, column, value.replace(tzinfo=None)).number_format = _XLSX_DATETIME
    elif isinstance(value, date):
        sheet.cell(row, column, value).number_format = _XLSX_DATE
    else:
        safe = safe_cell(value)
        # openpyxl refuses control characters, which free-text reasons may contain.
        sheet.cell(row, column, ILLEGAL_CHARACTERS_RE.sub("", safe) if isinstance(safe, str) else safe)


def to_xlsx(head: list[str], rows: list[list], info: ExportInfo) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = info.title[:31]
    sheet.append(head)
    sheet.freeze_panes = "A2"
    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row, start=1):
            _xlsx_cell(sheet, r, c, value)
    for c, name in enumerate(head, start=1):
        sheet.column_dimensions[get_column_letter(c)].width = max(14, len(name) + 2)

    about = book.create_sheet("Export Information")
    lines = [
        ("Report name", info.title),
        ("Reporting period from", info.period_from),
        ("Reporting period to", info.period_to),
        ("Generated date/time", info.generated_at),
        ("Time zone", info.time_zone),
        ("Employee filter (user ID)", info.user_id if info.user_id is not None else "All"),
        ("Work mode filter", info.work_mode or "All"),
        ("Rows", len(rows)),
        ("Date and time columns", f"Shown in {info.time_zone}. Work date is the local date of check-in."),
    ]
    for r, (label, value) in enumerate(lines, start=1):
        about.cell(r, 1, label)
        _xlsx_cell(about, r, 2, value)
    about.column_dimensions["A"].width = 28
    about.column_dimensions["B"].width = 48
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
