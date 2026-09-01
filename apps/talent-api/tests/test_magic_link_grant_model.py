"""MagicLinkGrant model — the derived ``status``/``is_valid`` contract and
the unique-token-hash guarantee the redeem path (later PR) relies on.

The status derivation is deliberately re-checked after a commit + fresh
load: SQLite drops tzinfo on a DateTime(timezone=True) round-trip, so a
naive ``expires_at`` must still compare correctly (it is always a UTC
instant — see the model docstring).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.magic_link_grant import MagicLinkGrant


def _client(db) -> Client:
    c = Client(name="Grant Model Client", platform_client_id="cli-grant-model", status="ACTIVE")
    db.add(c)
    db.commit()
    return c


def _grant(db, client_id: int, **overrides) -> MagicLinkGrant:
    now = datetime.now(UTC)
    fields = dict(
        public_id="mlg-modeltest01",
        client_id=client_id,
        contact_email="reviewer@client.example",
        contact_name="Reviewer",
        token_hash="a" * 64,
        token_prefix="abc12345",
        issued_by_user_id=99,
        issued_at=now,
        expires_at=now + timedelta(days=14),
    )
    fields.update(overrides)
    grant = MagicLinkGrant(**fields)
    db.add(grant)
    db.commit()
    return grant


def test_status_active_for_a_fresh_grant(db):
    client = _client(db)
    grant = _grant(db, client.id)
    assert grant.status == "ACTIVE"
    assert grant.is_valid is True


def test_status_expired_survives_sqlite_tzinfo_roundtrip(db):
    client = _client(db)
    _grant(db, client.id, expires_at=datetime.now(UTC) - timedelta(minutes=1))

    # Fresh session → expires_at comes back naive on SQLite; the property
    # must still resolve it as a past UTC instant, not raise.
    fresh = SessionLocal()
    try:
        reloaded = fresh.execute(select(MagicLinkGrant)).scalar_one()
        assert reloaded.status == "EXPIRED"
        assert reloaded.is_valid is False
    finally:
        fresh.close()


def test_status_revoked_takes_precedence_over_expiry(db):
    client = _client(db)
    grant = _grant(
        db,
        client.id,
        expires_at=datetime.now(UTC) - timedelta(days=1),
        revoked_at=datetime.now(UTC),
        revoked_by_user_id=7,
    )
    assert grant.status == "REVOKED"
    assert grant.is_valid is False


def test_token_hash_is_unique(db):
    client = _client(db)
    _grant(db, client.id, public_id="mlg-dup-a", token_hash="d" * 64)
    with pytest.raises(IntegrityError):
        _grant(db, client.id, public_id="mlg-dup-b", token_hash="d" * 64)


def test_defaults_scope_type_and_use_count(db):
    client = _client(db)
    now = datetime.now(UTC)
    grant = MagicLinkGrant(
        public_id="mlg-defaults01",
        client_id=client.id,
        token_hash="e" * 64,
        issued_by_user_id=1,
        issued_at=now,
        expires_at=now + timedelta(days=14),
    )
    db.add(grant)
    db.commit()
    assert grant.scope_type == "CLIENT_WORKSPACE"
    assert grant.use_count == 0
    assert grant.redeemed_at is None
    assert grant.revoked_at is None
