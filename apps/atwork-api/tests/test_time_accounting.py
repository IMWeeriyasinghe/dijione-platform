from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.services.time_accounting import daily_totals, local_day_bounds, session_totals, split_seconds_by_local_day

COLOMBO = ZoneInfo("Asia/Colombo")


@dataclass
class B:
    started_at: datetime
    ended_at: datetime | None


@dataclass
class S:
    check_in_at: datetime
    check_out_at: datetime | None
    breaks: list = field(default_factory=list)


def utc(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def test_gross_break_and_net():
    session = S(utc(9, 3), utc(9, 11), [B(utc(9, 6), utc(9, 6, 30)), B(utc(9, 9), utc(9, 9, 15))])
    totals = session_totals(session, utc(9, 12))
    assert (totals.gross_seconds, totals.break_seconds, totals.net_seconds) == (28800, 2700, 26100)


def test_open_session_and_open_break_run_to_now():
    totals = session_totals(S(utc(9, 3), None, [B(utc(9, 4), None)]), utc(9, 5))
    assert (totals.gross_seconds, totals.break_seconds, totals.net_seconds) == (7200, 3600, 3600)


def test_colombo_day_bounds_are_offset_from_utc():
    start, end = local_day_bounds(date(2026, 11, 9), COLOMBO)
    assert start == datetime(2026, 11, 8, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 11, 9, 18, 30, tzinfo=UTC)


def test_split_at_local_midnight_not_utc_midnight():
    # 22:30 to 02:30 Colombo crosses local midnight at 18:30 UTC.
    assert split_seconds_by_local_day(utc(9, 17), utc(9, 21), COLOMBO) == {date(2026, 11, 9): 5400, date(2026, 11, 10): 9000}
    # 23:00 UTC to 01:00 UTC stays within one Colombo day.
    assert split_seconds_by_local_day(utc(9, 23), utc(10, 1), COLOMBO) == {date(2026, 11, 10): 7200}


def test_cross_midnight_daily_totals_with_a_break_across_midnight():
    session = S(utc(9, 17), utc(9, 21), [B(utc(9, 18), utc(9, 19))])
    daily = daily_totals([session], COLOMBO, utc(10, 0))
    first, second = daily[date(2026, 11, 9)], daily[date(2026, 11, 10)]
    assert (first.gross_seconds, first.break_seconds, first.net_seconds) == (5400, 1800, 3600)
    assert (second.gross_seconds, second.break_seconds, second.net_seconds) == (9000, 1800, 7200)
    whole = session_totals(session, utc(10, 0))
    assert first.net_seconds + second.net_seconds == whole.net_seconds


def test_multi_day_span_and_extensible_time_zone():
    assert len(split_seconds_by_local_day(utc(1, 0), utc(4, 0), COLOMBO)) == 4
    assert split_seconds_by_local_day(utc(9, 23), utc(10, 1), ZoneInfo("UTC")) == {
        date(2026, 11, 9): 3600,
        date(2026, 11, 10): 3600,
    }
