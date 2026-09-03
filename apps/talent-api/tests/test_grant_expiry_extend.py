"""Grant expiry selection (POST /grants) + extend (POST
/grants/{id}/extend) — plan §H2/§H3.

User-selectable expiry, default 14d, min 1d, max 90d, no indefinite grants;
extending a grant moves expires_at forward on the SAME row (token_hash/
token_prefix/public_id untouched) so the client's existing URL keeps
working — never reissue for a routine expiry push. Extend-only (never
shortens); a revoked grant can never be extended; an expired-but-not-
revoked grant CAN be extended (re-activates the same URL).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import headers_for


def _parse(iso: str) -> datetime:
    """SQLite drops tzinfo on round-trip even for tz-aware columns — every
    value this service writes is UTC (MagicLinkService uses datetime.now(UTC)
    throughout), so a naive parse is always a UTC instant, same convention
    as MagicLinkGrant.status."""
    value = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def _create_grant(api_client, world, **overrides):
    payload = {"client_id": world["abc"].id, "contact_name": "Jane Doe", "contact_email": "jane@example.com"}
    payload.update(overrides)
    return api_client.post("/api/talent/external/grants", json=payload, headers=world["ta_headers"])


# --- expiry selection on create -----------------------------------------


def test_create_defaults_to_fourteen_days(api_client, db, two_tenant_world):
    resp = _create_grant(api_client, two_tenant_world)
    assert resp.status_code == 201
    body = resp.json()
    expires_at = _parse(body["expires_at"])
    delta = expires_at - datetime.now(UTC)
    assert timedelta(days=13, hours=23) < delta < timedelta(days=14, hours=1)


def test_create_accepts_an_explicit_expires_at_date(api_client, db, two_tenant_world):
    target = datetime.now(UTC) + timedelta(days=30)
    resp = _create_grant(api_client, two_tenant_world, expires_at=target.isoformat())
    assert resp.status_code == 201
    expires_at = _parse(resp.json()["expires_at"])
    assert abs((expires_at - target).total_seconds()) < 5


def test_create_still_accepts_expires_in_days(api_client, db, two_tenant_world):
    resp = _create_grant(api_client, two_tenant_world, expires_in_days=5)
    assert resp.status_code == 201
    expires_at = _parse(resp.json()["expires_at"])
    delta = expires_at - datetime.now(UTC)
    assert timedelta(days=4, hours=23) < delta < timedelta(days=5, hours=1)


def test_create_rejects_expires_at_beyond_ninety_days(api_client, db, two_tenant_world):
    target = datetime.now(UTC) + timedelta(days=200)
    resp = _create_grant(api_client, two_tenant_world, expires_at=target.isoformat())
    assert resp.status_code == 400


def test_create_rejects_expires_at_in_the_past(api_client, db, two_tenant_world):
    target = datetime.now(UTC) - timedelta(days=1)
    resp = _create_grant(api_client, two_tenant_world, expires_at=target.isoformat())
    assert resp.status_code == 400


def test_create_rejects_expires_in_days_out_of_bounds(api_client, db, two_tenant_world):
    # Field(ge=1, le=90) on the schema -> 422, not 400.
    assert _create_grant(api_client, two_tenant_world, expires_in_days=0).status_code == 422
    assert _create_grant(api_client, two_tenant_world, expires_in_days=91).status_code == 422


# --- extend ----------------------------------------------------------------


def test_extend_moves_expiry_forward_and_keeps_the_same_url(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=5).json()
    public_id = created["public_id"]
    old_token_prefix = created["token_prefix"]

    new_target = datetime.now(UTC) + timedelta(days=60)
    resp = api_client.post(
        f"/api/talent/external/grants/{public_id}/extend",
        json={"expires_at": new_target.isoformat()},
        headers=two_tenant_world["ta_headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["public_id"] == public_id
    assert body["token_prefix"] == old_token_prefix  # same grant, same URL
    expires_at = _parse(body["expires_at"])
    assert abs((expires_at - new_target).total_seconds()) < 5


def test_extend_accepts_expires_in_days_too(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=5).json()
    resp = api_client.post(
        f"/api/talent/external/grants/{created['public_id']}/extend",
        json={"expires_in_days": 30},
        headers=two_tenant_world["ta_headers"],
    )
    assert resp.status_code == 200
    expires_at = _parse(resp.json()["expires_at"])
    delta = expires_at - datetime.now(UTC)
    assert timedelta(days=29, hours=23) < delta < timedelta(days=30, hours=1)


def test_extend_cannot_shorten_expiry(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=60).json()
    earlier = datetime.now(UTC) + timedelta(days=5)
    resp = api_client.post(
        f"/api/talent/external/grants/{created['public_id']}/extend",
        json={"expires_at": earlier.isoformat()},
        headers=two_tenant_world["ta_headers"],
    )
    assert resp.status_code == 400


def test_extend_rejects_out_of_bounds_target(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=5).json()
    too_far = datetime.now(UTC) + timedelta(days=200)
    resp = api_client.post(
        f"/api/talent/external/grants/{created['public_id']}/extend",
        json={"expires_at": too_far.isoformat()},
        headers=two_tenant_world["ta_headers"],
    )
    assert resp.status_code == 400


def test_revoked_grant_cannot_be_extended(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=30).json()
    public_id = created["public_id"]
    api_client.post(f"/api/talent/external/grants/{public_id}/revoke", headers=two_tenant_world["ta_headers"])

    resp = api_client.post(
        f"/api/talent/external/grants/{public_id}/extend",
        json={"expires_in_days": 10},
        headers=two_tenant_world["ta_headers"],
    )
    assert resp.status_code == 400
    assert "regenerate" in resp.json()["detail"].lower()


def test_expired_but_not_revoked_grant_can_be_extended(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=1).json()
    public_id = created["public_id"]

    from app.repositories.magic_link_grant_repo import MagicLinkGrantRepository

    grant = MagicLinkGrantRepository(db).get_by_public_id(public_id)
    grant.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    assert grant.status == "EXPIRED"

    resp = api_client.post(
        f"/api/talent/external/grants/{public_id}/extend",
        json={"expires_in_days": 14},
        headers=two_tenant_world["ta_headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"


def test_extend_requires_staff_scope(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=30).json()
    resp = api_client.post(
        f"/api/talent/external/grants/{created['public_id']}/extend",
        json={"expires_in_days": 10},
        headers=headers_for(999, full_name="Client User", role="TALENT_CLIENT", client_id=two_tenant_world["abc"].id),
    )
    assert resp.status_code == 403


def test_extend_out_of_portfolio_grant_is_404(api_client, db, two_tenant_world):
    created = _create_grant(api_client, two_tenant_world, expires_in_days=30).json()
    portfolio_headers = headers_for(
        888, full_name="Portfolio TA", role="TA_MEMBER", client_ids=[two_tenant_world["xyz"].id]
    )
    resp = api_client.post(
        f"/api/talent/external/grants/{created['public_id']}/extend",
        json={"expires_in_days": 10},
        headers=portfolio_headers,
    )
    assert resp.status_code == 404
