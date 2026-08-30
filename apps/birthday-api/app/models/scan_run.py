from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScanRun(Base):
    """Audit record of one detection-scan execution (plan §U) — replaces
    the previous "the only record of a run is its synchronous HTTP
    response" gap and backs GET /internal/scan-runs (previously a 501)."""

    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="MANUAL")  # SCHEDULED | MANUAL
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    employees_scanned: Mapped[int] = mapped_column(Integer, default=0)
    orders_created: Mapped[int] = mapped_column(Integer, default=0)
    orders_existing: Mapped[int] = mapped_column(Integer, default=0)
    exceptions: Mapped[int] = mapped_column(Integer, default=0)
    ineligible_skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
