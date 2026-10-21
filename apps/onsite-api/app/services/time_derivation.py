"""Explicitly derived local-time fields. The raw source values are never
changed — these are computed alongside them and stored in clearly named
derived columns."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def site_local_date(punch_time_local: str) -> date:
    """The calendar date of the source's own local wall clock
    (``PunchTimeLocal``, ISO-8601 with offset)."""
    return date.fromisoformat(punch_time_local[:10])


def tz_consistent(punch_time_local: str, punch_time_utc: datetime, site_time_zone: str | None) -> bool | None:
    """True when ``PunchTimeUtc`` converted with the site's configured IANA
    time zone equals the source ``PunchTimeLocal`` (wall time AND offset).
    None when the site time zone is unknown/invalid."""
    if not site_time_zone:
        return None
    try:
        tz = ZoneInfo(site_time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    try:
        source_local = datetime.fromisoformat(punch_time_local)
    except ValueError:
        return False
    expected = punch_time_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    return (
        expected.replace(tzinfo=None) == source_local.replace(tzinfo=None)
        and expected.utcoffset() == source_local.utcoffset()
    )


def site_today(site_time_zone: str | None, now_utc: datetime | None = None) -> date:
    """"Today" for a site = now in the site's configured time zone."""
    now = now_utc or datetime.now(ZoneInfo("UTC"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("UTC"))
    try:
        return now.astimezone(ZoneInfo(site_time_zone)).date() if site_time_zone else now.date()
    except (ZoneInfoNotFoundError, ValueError):
        return now.date()
