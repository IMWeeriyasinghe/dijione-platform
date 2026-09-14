"""Schemas for the DijiBirthday-local non-production Email Safety
allowlist (BirthdayTestEmailRecipient). See
docs/platform/email-architecture.md."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

RECIPIENT_TYPES = ("INTERNAL_TESTER", "TEST_SUPPLIER")


class TestEmailRecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_address: str
    display_label: str
    recipient_type: str
    is_active: bool
    created_by: int | None
    updated_by: int | None
    created_at: datetime
    updated_at: datetime


class TestEmailRecipientListResponse(BaseModel):
    items: list[TestEmailRecipientRead]


class TestEmailRecipientCreate(BaseModel):
    # Plain str, not pydantic's EmailStr — that extra needs the
    # email-validator package, which is not (and should not become) a
    # birthday-api dependency just for this one field. Real syntax
    # validation happens in app/services/test_email_recipient_service.py's
    # normalize_email(), matching this repo's convention of validating in
    # the service layer rather than via a pydantic extra.
    email_address: str
    display_label: str = ""
    recipient_type: str = "INTERNAL_TESTER"
    is_active: bool = True


class TestEmailRecipientUpdate(BaseModel):
    # All optional — PATCH-style partial update (label, type, active flag).
    # email_address is intentionally NOT editable here: changing the
    # address a row represents is modeled as delete+recreate, so the
    # normalized-uniqueness index and audit trail stay unambiguous.
    display_label: str | None = None
    recipient_type: str | None = None
    is_active: bool | None = None
