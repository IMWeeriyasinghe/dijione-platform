from __future__ import annotations

from sqlalchemy import Integer
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

    # No FK to `users.id` — User is owned by platform-api's own database.
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
