"""Realistic in-memory stand-in for the Azure SQL ``onsite`` schema (CI and
local dev, ``INTEGRATIONS_MODE=mock``).

Covers: epoch 1 and epoch 1000 coexisting at one site; matched and
unmatched EmpCodes (including a leading-zero code kept verbatim); a
single-punch day; a possible duplicate tap (two punches 20 s apart); a
second site in a DST-observing time zone (Australia/Sydney), including an
event with an inconsistent local offset; ``PunchState`` raw ``255``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.attendance_source.client import (
    OnsiteSourceClient,
    SourceAgentStatusRow,
    SourceEpochTotals,
    SourceEventRow,
    SourceSiteRow,
)

_COLOMBO = "Asia/Colombo"
_SYDNEY = "Australia/Sydney"
_BASE_RECEIVED = datetime(2026, 10, 14, 12, 0, 0)


def _local_iso(utc: datetime, tz: str, *, offset_override: str | None = None) -> str:
    local = utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz))
    text = local.strftime("%Y-%m-%dT%H:%M:%S")
    offset = local.strftime("%z")
    offset = offset_override or f"{offset[:3]}:{offset[3:]}"
    return f"{text}{offset}"


def _event(n: int, site: str, epoch: int, tx: int, emp: str, utc: datetime, tz: str, *,
           offset_override: str | None = None, received_offset: int = 0) -> SourceEventRow:
    return SourceEventRow(
        event_id=f"{site}:{epoch}:{tx}", site_id=site, source_epoch=epoch, source_transaction_id=tx,
        emp_code=emp, emp_id=None, punch_time_local=_local_iso(utc, tz, offset_override=offset_override),
        punch_time_utc=utc, time_zone=tz, punch_state="255", verify_type=1, work_code=None,
        terminal_sn="TERM-01", terminal_alias="Main Door", area_alias="Ground Floor", source=1,
        is_attendance=True, upload_time_utc=utc + timedelta(seconds=5), captured_at_utc=utc + timedelta(seconds=10),
        received_utc=_BASE_RECEIVED + timedelta(seconds=n + received_offset), batch_id=f"BATCH-{epoch}-{n // 5}",
        record_hash=f"hash-{site}-{epoch}-{tx}",
    )


def _build_events() -> list[SourceEventRow]:
    d1 = datetime(2026, 10, 13, 3, 0, 0)  # 08:30 Colombo
    d2 = datetime(2026, 10, 14, 3, 15, 0)
    rows = [
        # dev-site, epoch 1000 (historical import)
        _event(1, "dev-site", 1000, 101, "101", d1, _COLOMBO),
        _event(2, "dev-site", 1000, 102, "101", d1 + timedelta(hours=9), _COLOMBO),
        _event(3, "dev-site", 1000, 103, "102", d1 + timedelta(minutes=5), _COLOMBO),  # single punch that day
        _event(4, "dev-site", 1000, 104, "0107", d1 + timedelta(minutes=7), _COLOMBO),  # leading zero verbatim
        _event(5, "dev-site", 1000, 105, "0107", d1 + timedelta(minutes=7, seconds=20), _COLOMBO),  # dup-like tap
        _event(6, "dev-site", 1000, 106, "999", d1 + timedelta(minutes=9), _COLOMBO),  # unmatched code
        _event(7, "dev-site", 1000, 107, "103", d2, _COLOMBO),  # inactive employee activity
        _event(8, "dev-site", 1000, 108, "105", d2 + timedelta(minutes=2), _COLOMBO),  # ambiguous number
        _event(9, "dev-site", 1000, 109, "101", d2 + timedelta(minutes=3), _COLOMBO),
        # dev-site, epoch 1 (live pipeline events) — coexist with epoch 1000
        _event(10, "dev-site", 1, 43594, "TEST-AZURE-001", d2 + timedelta(hours=1), _COLOMBO),
        # second site in a DST time zone
        _event(11, "syd-site", 1, 1, "110", datetime(2026, 10, 13, 22, 0, 0), _SYDNEY),  # 09:00 AEDT
        _event(12, "syd-site", 1, 2, "110", datetime(2026, 10, 14, 6, 0, 0), _SYDNEY),
        _event(13, "syd-site", 1, 3, "108", datetime(2026, 10, 14, 22, 30, 0), _SYDNEY, offset_override="+10:00"),
    ]
    return rows


class MockOnsiteSource(OnsiteSourceClient):
    def __init__(self, events: list[SourceEventRow] | None = None) -> None:
        self.events = events if events is not None else _build_events()

    def list_sites(self) -> list[SourceSiteRow]:
        return [
            SourceSiteRow("dev-site", "DEV Site (Colombo)", _COLOMBO, True, datetime(2026, 10, 20)),
            SourceSiteRow("syd-site", "Sydney Office", _SYDNEY, True, datetime(2026, 10, 20)),
        ]

    def read_events_after(self, received_after, event_id_after, limit):
        ordered = sorted(self.events, key=lambda e: (e.received_utc, e.event_id))
        if received_after is not None:
            ordered = [e for e in ordered if (e.received_utc, e.event_id) > (received_after, event_id_after)]
        return ordered[:limit]

    def list_agent_status(self) -> list[SourceAgentStatusRow]:
        return [
            SourceAgentStatusRow(
                site_id="dev-site", agent_instance_id="agent-1", agent_version="1.0.0", health="Healthy",
                health_reason=None, source_epoch=1, high_water_id=43594, source_connected=True,
                last_source_poll_utc=_BASE_RECEIVED, last_delivery_utc=_BASE_RECEIVED, pending_count=0,
                dead_letter_count=0, oldest_pending_age_seconds=None, last_error=None,
                last_heartbeat_utc=_BASE_RECEIVED, heartbeat_count=100,
            )
        ]

    def epoch_totals(self) -> list[SourceEpochTotals]:
        totals: dict[tuple[str, int], list] = {}
        for e in self.events:
            t = totals.setdefault((e.site_id, e.source_epoch), [0, None])
            t[0] += 1
            t[1] = e.received_utc if t[1] is None else max(t[1], e.received_utc)
        return [SourceEpochTotals(s, ep, c, m) for (s, ep), (c, m) in sorted(totals.items())]
