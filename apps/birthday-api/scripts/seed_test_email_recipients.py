"""One-off, idempotent bootstrap of the initial approved DEV test email
recipients (app/models/birthday_test_email_recipient.py — the DijiBirthday
Email Safety allowlist, docs/platform/email-architecture.md).

Deliberately a script, not baked into an Alembic migration: this is
environment-specific bootstrap DATA (real test-person addresses), not a
schema change — this repo's migrations only ever change schema, never seed
business data (see docs/birthday for the general convention), and these
addresses must never propagate automatically to UAT (which gets its own
independent Email Safety records, added by an administrator through the UI
there). Safe to re-run: skips any address that already exists (matched by
normalized_email_address), never overwrites an existing row's is_active/
label/type — once created, a recipient is only ever edited through the
Email Safety admin UI, never by re-running this script.

Usage (from apps/birthday-api):
    python -m scripts.seed_test_email_recipients
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.birthday_test_email_recipient import BirthdayTestEmailRecipient
from app.services import test_email_recipient_service as recipients

_INITIAL_DEV_RECIPIENTS = [
    {
        "email_address": "madushanka.weeriyasinghe@dijitalteam.com",
        "display_label": "Madushanka - Internal Test",
        "recipient_type": "INTERNAL_TESTER",
        "is_active": True,
    },
    {
        "email_address": "madusankaweeriyasinghe20@gmail.com",
        "display_label": "Test Supplier - Gmail",
        "recipient_type": "TEST_SUPPLIER",
        "is_active": True,
    },
]


def run() -> dict:
    db = SessionLocal()
    created: list[str] = []
    already_existed: list[str] = []
    try:
        for entry in _INITIAL_DEV_RECIPIENTS:
            normalized = recipients.normalize_email(entry["email_address"])
            existing = db.execute(
                select(BirthdayTestEmailRecipient).where(
                    BirthdayTestEmailRecipient.normalized_email_address == normalized
                )
            ).scalars().first()
            if existing is not None:
                already_existed.append(entry["email_address"])
                continue
            recipients.create_recipient(
                db, email_address=entry["email_address"], display_label=entry["display_label"],
                recipient_type=entry["recipient_type"], is_active=entry["is_active"], actor_id=None,
            )
            created.append(entry["email_address"])
        db.commit()
    finally:
        db.close()

    summary = {"created": created, "already_existed": already_existed}
    print("Seed complete:", summary)
    return summary


if __name__ == "__main__":
    run()
