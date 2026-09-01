from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Employee(TimestampMixin, Base):
    """The durable People / Workforce read model — BambooHR employee facts,
    refreshed on every sync. This is the read model that did not exist
    before Wave E (birthday-api previously made a live BambooHR call per
    request/scan with nothing persisted).

    Keyed on the stable BambooHR internal ``id`` (``bamboohr_id``); the
    human-facing ``employee_number`` is a separate, nullable field (can be
    blank for some records — confirmed live). No PII beyond what
    consumers already needed (name, work email, birthday MM-DD, address for
    delivery) — never salary/compensation/personal email/phone.
    """

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bamboohr_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    employee_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    full_name: Mapped[str] = mapped_column(String(255), default="")
    work_email: Mapped[str] = mapped_column(String(255), default="")
    birth_month: Mapped[int] = mapped_column(Integer, default=0)
    birth_day: Mapped[int] = mapped_column(Integer, default=0)
    department: Mapped[str] = mapped_column(String(255), default="")
    office_location: Mapped[str] = mapped_column(String(255), default="")
    employment_status: Mapped[str] = mapped_column(String(32), default="Active")
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Residential/delivery address snapshot (never written back to BambooHR).
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state_province: Mapped[str | None] = mapped_column(String(128), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
