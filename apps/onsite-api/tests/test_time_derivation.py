from datetime import date, datetime

from app.models.mirror import AttendanceEvent
from app.services.time_derivation import site_local_date, site_today, tz_consistent
from tests.conftest import run_sync


def test_site_local_date_uses_source_local_wall_clock():
    # 23:50 local on the 13th is the 13th, even though UTC is the 13th 18:20
    assert site_local_date("2026-10-13T23:50:00+05:30") == date(2026, 10, 13)
    # 00:10 local on the 14th is the 14th although UTC is still the 13th
    assert site_local_date("2026-10-14T00:10:00+05:30") == date(2026, 10, 14)


def test_tz_consistent_colombo():
    assert tz_consistent("2026-10-14T08:45:00+05:30", datetime(2026, 10, 14, 3, 15), "Asia/Colombo") is True
    assert tz_consistent("2026-10-14T08:45:00+05:00", datetime(2026, 10, 14, 3, 45), "Asia/Colombo") is False
    assert tz_consistent("2026-10-14T08:45:00+05:30", datetime(2026, 10, 14, 3, 15), "") is None
    assert tz_consistent("2026-10-14T08:45:00+05:30", datetime(2026, 10, 14, 3, 15), "Not/AZone") is None


def test_tz_consistent_dst_sydney():
    # 2026-10-14 is AEDT (+11:00); 2026-06-14 is AEST (+10:00)
    assert tz_consistent("2026-10-14T09:00:00+11:00", datetime(2026, 10, 13, 22, 0), "Australia/Sydney") is True
    assert tz_consistent("2026-06-14T09:00:00+10:00", datetime(2026, 6, 13, 23, 0), "Australia/Sydney") is True
    assert tz_consistent("2026-10-15T08:30:00+10:00", datetime(2026, 10, 14, 22, 30), "Australia/Sydney") is False


def test_site_today_uses_site_time_zone():
    utc = datetime(2026, 10, 13, 20, 0)
    assert site_today("Asia/Colombo", utc) == date(2026, 10, 14)  # 01:30 next day
    assert site_today("Australia/Sydney", utc) == date(2026, 10, 14)
    assert site_today("UTC", utc) == date(2026, 10, 13)


def test_mirror_derives_fields_per_site_time_zone(api_client, db):
    run_sync(api_client)
    rows = {e.event_id: e for e in db.query(AttendanceEvent).all()}
    assert rows["syd-site:1:1"].site_local_date == date(2026, 10, 14)  # 22:00Z = 09:00 AEDT next day
    assert rows["syd-site:1:1"].tz_consistent is True
    assert rows["syd-site:1:3"].tz_consistent is False  # source offset +10:00 during DST
    assert all(r.tz_consistent for k, r in rows.items() if k.startswith("dev-site"))
