"""DijiBirthday-owned, non-production recipient safety allowlist. Governs
who DEV/UAT may actually SEND outbound Graph email TO — entirely separate
from (and layered on top of) Exchange RBAC for Applications, which governs
which mailbox this service may SEND AS. See docs/platform/email-architecture.md.

Deliberately has NO environment column: DijiBirthday DEV/UAT/PROD already
use separate databases (docs/platform/deployment-topology.md), so this
table's rows are already environment-isolated by which database they live
in — an explicit environment column here would be redundant and could
invite an environment-crossing bug (an unfiltered query would need to
remember to filter it). PROD's own database simply never gets rows here,
and the mail-policy integration never consults this table in "production"
policy mode regardless (app/integrations/factory.py)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BirthdayTestEmailRecipient(TimestampMixin, Base):
    __tablename__ = "birthday_test_email_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_address: Mapped[str] = mapped_column(String(255))
    # trimmed + lowercased email_address — the sole uniqueness/match key
    # (see app/services/test_email_recipient_service.py's normalize_email).
    normalized_email_address: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_label: Mapped[str] = mapped_column(String(255), default="")
    # INTERNAL_TESTER | TEST_SUPPLIER
    recipient_type: Mapped[str] = mapped_column(String(32), default="INTERNAL_TESTER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
