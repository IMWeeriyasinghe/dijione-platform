"""TA magic-link grant management API (plan B.11): generate / list / revoke
/ regenerate, portfolio scoping, audit events, and the end-to-end tie-in
that a generated link actually redeems and a revoked one stops.
"""

from __future__ import annotations

import pytest

from app.core.rate_limit import redeem_rate_limiter
from tests.conftest import headers_for


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    redeem_rate_limiter.reset()
    yield
    redeem_rate_limiter.reset()


@pytest.fixture()
def clients(db):
    from app.models.client import Client

    abc = Client(name="ABC Company", platform_client_id="cli-abc-company", status="ACTIVE")
    xyz = Client(name="XYZ Company", platform_client_id="cli-xyz-company", status="ACTIVE")
    db.add_all([abc, xyz])
    db.commit()
    return {"abc": abc, "xyz": xyz}


def _staff():
    # Unrestricted staff — TA_MEMBER with no portfolio restriction.
    return headers_for(900, full_name="TA Member", role="TA_MEMBER")


def _portfolio_staff(client_id: int):
    return headers_for(901, full_name="Portfolio TA", role="TA_MEMBER", client_ids=[client_id])


# --- generate ----------------------------------------------------------


def test_staff_can_generate_a_grant_and_gets_the_url_once(api_client, clients):
    resp = api_client.post(
        "/api/talent/external/grants",
        headers=_staff(),
        json={"client_id": clients["abc"].id, "contact_name": "Jo", "contact_email": "jo@abc.example"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["client_name"] == "ABC Company"
    assert body["use_count"] == 0 and body["redeemed_at"] is None
    assert body["raw_token"] and body["raw_token"] not in body["token_prefix"]
    assert body["access_url"].endswith("#" + body["raw_token"])
    assert "/access#" in body["access_url"]


def test_generate_is_staff_only(api_client, db, clients):
    from tests.conftest import external_headers_for

    client_headers = headers_for(
        5, full_name="ABC Client", role="TALENT_CLIENT", client_id=clients["abc"].id
    )
    assert (
        api_client.post(
            "/api/talent/external/grants", headers=client_headers, json={"client_id": clients["abc"].id}
        ).status_code
        == 403
    )
    # An external magic-link session must not reach this internal route at all.
    ext = external_headers_for(db, clients["abc"])
    assert (
        api_client.post(
            "/api/talent/external/grants", headers=ext, json={"client_id": clients["abc"].id}
        ).status_code
        == 401
    )


def test_generate_unknown_client_is_404(api_client, clients):
    assert (
        api_client.post(
            "/api/talent/external/grants", headers=_staff(), json={"client_id": 999999}
        ).status_code
        == 404
    )


def test_generate_emits_link_generated_audit(api_client, clients, platform_calls):
    api_client.post(
        "/api/talent/external/grants", headers=_staff(), json={"client_id": clients["abc"].id}
    )
    actions = [e["action"] for e in platform_calls["audit_events"]]
    assert "talent.external.link_generated" in actions
    ev = next(e for e in platform_calls["audit_events"] if e["action"] == "talent.external.link_generated")
    assert "raw_token" not in str(ev)


# --- list ------------------------------------------------------------


def test_list_grants_shows_history_without_the_raw_token(api_client, clients):
    api_client.post(
        "/api/talent/external/grants", headers=_staff(), json={"client_id": clients["abc"].id}
    )
    resp = api_client.get("/api/talent/external/grants", headers=_staff())
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert "raw_token" not in rows[0] and "access_url" not in rows[0]
    assert "token_hash" not in rows[0]
    assert rows[0]["token_prefix"]


def test_list_can_filter_by_client(api_client, clients):
    for c in ("abc", "xyz"):
        api_client.post(
            "/api/talent/external/grants", headers=_staff(), json={"client_id": clients[c].id}
        )
    rows = api_client.get(
        "/api/talent/external/grants", headers=_staff(), params={"client_id": clients["abc"].id}
    ).json()
    assert len(rows) == 1 and rows[0]["client_id"] == clients["abc"].id


# --- revoke / regenerate --------------------------------------------


def test_revoke_marks_the_grant_and_kills_redemption(api_client, clients):
    created = api_client.post(
        "/api/talent/external/grants", headers=_staff(), json={"client_id": clients["abc"].id}
    ).json()
    raw = created["raw_token"]
    assert api_client.post("/api/talent/external/redeem", json={"token": raw}).status_code == 200

    revoked = api_client.post(
        f"/api/talent/external/grants/{created['public_id']}/revoke", headers=_staff()
    )
    assert revoked.status_code == 200 and revoked.json()["status"] == "REVOKED"
    assert api_client.post("/api/talent/external/redeem", json={"token": raw}).status_code == 401


def test_regenerate_revokes_the_old_and_issues_a_working_new_one(api_client, clients, platform_calls):
    created = api_client.post(
        "/api/talent/external/grants",
        headers=_staff(),
        json={"client_id": clients["abc"].id, "contact_email": "keep@abc.example"},
    ).json()
    old_raw = created["raw_token"]

    regen = api_client.post(
        f"/api/talent/external/grants/{created['public_id']}/regenerate", headers=_staff()
    )
    assert regen.status_code == 200
    new_body = regen.json()
    assert new_body["public_id"] != created["public_id"]
    assert new_body["status"] == "ACTIVE"
    assert new_body["contact_email"] == "keep@abc.example"  # carried over

    assert api_client.post("/api/talent/external/redeem", json={"token": old_raw}).status_code == 401
    assert (
        api_client.post(
            "/api/talent/external/redeem", json={"token": new_body["raw_token"]}
        ).status_code
        == 200
    )
    actions = [e["action"] for e in platform_calls["audit_events"]]
    assert "talent.external.link_regenerated" in actions


def test_revoke_unknown_public_id_is_404(api_client):
    assert (
        api_client.post(
            "/api/talent/external/grants/mlg-nope/revoke", headers=_staff()
        ).status_code
        == 404
    )


# --- portfolio scoping ---------------------------------------------


def test_portfolio_staff_cannot_generate_outside_their_portfolio(api_client, clients):
    headers = _portfolio_staff(clients["abc"].id)
    ok = api_client.post(
        "/api/talent/external/grants", headers=headers, json={"client_id": clients["abc"].id}
    )
    assert ok.status_code == 201
    denied = api_client.post(
        "/api/talent/external/grants", headers=headers, json={"client_id": clients["xyz"].id}
    )
    assert denied.status_code == 404  # no signal that XYZ exists


def test_portfolio_staff_list_and_revoke_are_scoped(api_client, clients):
    # An unrestricted TA issues a grant for XYZ.
    xyz_grant = api_client.post(
        "/api/talent/external/grants", headers=_staff(), json={"client_id": clients["xyz"].id}
    ).json()

    pf = _portfolio_staff(clients["abc"].id)
    assert api_client.get("/api/talent/external/grants", headers=pf).json() == []
    assert (
        api_client.get(
            "/api/talent/external/grants", headers=pf, params={"client_id": clients["xyz"].id}
        ).json()
        == []
    )
    assert (
        api_client.post(
            f"/api/talent/external/grants/{xyz_grant['public_id']}/revoke", headers=pf
        ).status_code
        == 404
    )


def test_expires_in_days_is_bounded(api_client, clients):
    too_long = api_client.post(
        "/api/talent/external/grants",
        headers=_staff(),
        json={"client_id": clients["abc"].id, "expires_in_days": 400},
    )
    assert too_long.status_code == 422  # no effectively-indefinite links
