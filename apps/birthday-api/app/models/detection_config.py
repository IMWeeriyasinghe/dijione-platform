from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BirthdayDetectionConfig(TimestampMixin, Base):
    """Admin-editable, versioned/singleton row driving detection thresholds
    and scan window — never hardcoded to a fixed lookahead in the detection
    service."""

    __tablename__ = "birthday_detection_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normal_threshold_days: Mapped[int] = mapped_column(Integer, default=10)
    short_notice_threshold_days: Mapped[int] = mapped_column(Integer, default=5)
    urgent_threshold_days: Mapped[int] = mapped_column(Integer, default=2)
    window_lookback_days: Mapped[int] = mapped_column(Integer, default=1)
    window_lookahead_days: Mapped[int] = mapped_column(Integer, default=14)

    # Semi-automation config (plan §U/§29) — every default/threshold that
    # drives auto-release is business-tunable, never hardcoded.
    default_quantity: Mapped[int] = mapped_column(Integer, default=1)
    verify_buffer_days: Mapped[int] = mapped_column(Integer, default=2)
    acknowledgement_sla_hours: Mapped[int] = mapped_column(Integer, default=24)
    # Global incident switch (plan §K/§Y): when False, no order is
    # auto-released on verification — every verified order routes to
    # REQUIRES_REVIEW instead, regardless of how "standard" it looks.
    auto_release_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Operational go-live boundary (V1 clean start). The first birthday
    # occurrence eligible for processing is operational_start_date +
    # supplier_lead_time_days. NULL start date = no boundary. The global
    # lead time is used ONLY for this boundary; per-supplier lead_time_days
    # still drives on-hold routing and verify-by dates.
    operational_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier_lead_time_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")

    # One-time clean-start record: set when an admin explicitly confirms the
    # pre-launch backlog exclusion. Once set, the exclusion cannot run again,
    # so later settings changes never cancel operational orders.
    clean_start_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clean_start_applied_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clean_start_excluded_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clean_start_first_eligible: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Internal P&C email alerts for supplier activity (messages, issues,
    # cannot-fulfil): comma/newline separated addresses, admin-managed in
    # Operational Settings. Empty = no email alerts (in-app ones still go).
    ops_alert_recipients: Mapped[str | None] = mapped_column(Text, nullable=True)

    # No FK to `users.id` — User is owned by platform-api's own database.
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
