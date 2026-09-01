"""Magic-link external client access (plan B.2/B.5/B.6/B.7/B.12/B.17):
redeem -> scoped session -> per-request grant re-check, cross-client
isolation, client-visibility gating, the signing trust boundary in both
directions, and redeem rate limiting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.constants import EXTERNAL_SESSION_PERMISSIONS
from app.core.rate_limit import redeem_rate_limiter
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.talent_request import TalentRequest
from tests.conftest import external_headers_for, headers_for, make_magic_link_grant

_INTERNAL_SECRET = "test-only-secret"  # matches conftest's JWT_DEV_SECRET


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    redeem_rate_limiter.reset()
    yield
    redeem_rate_limiter.reset()


@pytest.fixture()
def world(db):
    from app.models.client import Client

    abc = Client(name="ABC Company", platform_client_id="cli-abc-company", status="ACTIVE")
    xyz = Client(name="XYZ Company", platform_client_id="cli-xyz-company", status="ACTIVE")
    db.add_all([abc, xyz])
    db.commit()

    def _request(client, designation, *, visible_candidate=True):
        tr = TalentRequest(
            request_code=f"SR-{client.id:03d}{len(designation)}",
            client_id=client.id,
            designation=designation,
            description="",
            current_stage="SOURCING",
            lifecycle_status="IN_PROGRESS",
            customer_success_status="APPROVED",
            ta_status="ATS_LINKED",
            client_safe_status_text="Sourcing",
            created_by=0,
        )
        db.add(tr)
        db.flush()
        cand = Candidate(
            full_name=f"Cand {designation}",
            email=None,
            professional_title="Engineer",
            summary="",
            source="LEVER",
            availability_status="IN_PROCESS",
        )
        db.add(cand)
        db.flush()
        db.add(
            Application(
                candidate_id=cand.id,
                talent_request_id=tr.id,
                current_stage="SOURCING",
                status="ACTIVE",
                is_client_visible=visible_candidate,
            )
        )
        db.commit()
        return tr

    return {
        "abc": abc,
        "xyz": xyz,
        "abc_req": _request(abc, "ABC Role", visible_candidate=True),
        "abc_req_hidden": _request(abc, "ABC Hidden Role", visible_candidate=False),
        "xyz_req": _request(xyz, "XYZ Role", visible_candidate=True),
    }


# --- redeem ---------------------------------------------------------------


def test_redeem_valid_token_returns_a_session(api_client, db, world):
    _, raw = make_magic_link_grant(db, world["abc"])
    resp = api_client.post("/api/talent/external/redeem", json={"token": raw})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert 0 < body["expires_in"] <= 60 * 60
    claims = jwt.get_unverified_claims(body["access_token"])
    assert claims["iss"] == get_settings().external_session_jwt_issuer
    assert claims["external"]["grant_id"]
    assert set(claims["module_roles"]["talent-flow"]["permissions"]) == set(
        EXTERNAL_SESSION_PERMISSIONS
    )


def test_redeem_bumps_counters_and_sets_redeemed_at_once(api_client, db, world):
    grant, raw = make_magic_link_grant(db, world["abc"])
    api_client.post("/api/talent/external/redeem", json={"token": raw})
    api_client.post("/api/talent/external/redeem", json={"token": raw})
    db.refresh(grant)
    assert grant.use_count == 2
    assert grant.last_used_at is not None
    first_redeemed = grant.redeemed_at
    assert first_redeemed is not None
    api_client.post("/api/talent/external/redeem", json={"token": raw})
    db.refresh(grant)
    assert grant.redeemed_at == first_redeemed  # set once, never moved


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda g: setattr(g, "revoked_at", datetime.now(UTC)), id="revoked"),
        pytest.param(
            lambda g: setattr(g, "expires_at", datetime.now(UTC) - timedelta(minutes=1)),
            id="expired",
        ),
    ],
)
def test_redeem_failure_modes_are_indistinguishable(api_client, db, world, mutate):
    grant, raw = make_magic_link_grant(db, world["abc"])
    mutate(grant)
    db.commit()

    revoked_resp = api_client.post("/api/talent/external/redeem", json={"token": raw})
    unknown_resp = api_client.post(
        "/api/talent/external/redeem", json={"token": "totally-unknown-token-value"}
    )
    assert revoked_resp.status_code == unknown_resp.status_code == 401
    assert revoked_resp.json() == unknown_resp.json()
    assert "ABC" not in revoked_resp.text  # no client name leak


def test_redeem_rejects_blank_token(api_client):
    assert api_client.post("/api/talent/external/redeem", json={"token": " "}).status_code == 401
    assert api_client.post("/api/talent/external/redeem", json={}).status_code == 422


# --- scoped session + per-request re-check ------------------------------


def test_session_reads_are_scoped_to_the_grants_client(api_client, db, world):
    headers = external_headers_for(db, world["abc"])
    resp = api_client.get("/api/talent/external/requests", headers=headers)
    assert resp.status_code == 200
    designations = {r["designation"] for r in resp.json()}
    assert designations == {"ABC Role", "ABC Hidden Role"}  # never XYZ's


def test_dashboard_and_interviews_require_a_session(api_client):
    assert api_client.get("/api/talent/external/dashboard").status_code in (401, 403)
    assert api_client.get("/api/talent/external/interviews").status_code in (401, 403)


def test_revoke_mid_session_blocks_the_next_request(api_client, db, world):
    grant, raw = make_magic_link_grant(db, world["abc"])
    from app.services.magic_link_service import MagicLinkService

    token, _ = MagicLinkService(db).mint_session_jwt(grant)
    headers = {"Authorization": f"Bearer {token}"}
    assert api_client.get("/api/talent/external/requests", headers=headers).status_code == 200

    grant.revoked_at = datetime.now(UTC)
    db.commit()
    blocked = api_client.get("/api/talent/external/requests", headers=headers)
    assert blocked.status_code == 401


def test_expiry_mid_session_blocks_the_next_request(api_client, db, world):
    grant, _ = make_magic_link_grant(db, world["abc"])
    from app.services.magic_link_service import MagicLinkService

    token, _ = MagicLinkService(db).mint_session_jwt(grant)
    headers = {"Authorization": f"Bearer {token}"}
    assert api_client.get("/api/talent/external/requests", headers=headers).status_code == 200

    grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert api_client.get("/api/talent/external/requests", headers=headers).status_code == 401


def test_session_pointing_at_a_missing_grant_is_401(api_client, db, world):
    grant, _ = make_magic_link_grant(db, world["abc"])
    from app.services.magic_link_service import MagicLinkService

    token, _ = MagicLinkService(db).mint_session_jwt(grant)
    db.delete(grant)
    db.commit()
    assert (
        api_client.get(
            "/api/talent/external/requests", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


# --- cross-client isolation ------------------------------------------------


def test_external_client_cannot_read_another_clients_request(api_client, db, world):
    headers = external_headers_for(db, world["abc"])
    resp = api_client.get(
        f"/api/talent/external/requests/{world['xyz_req'].id}", headers=headers
    )
    assert resp.status_code == 404  # no existence leak


def test_external_client_cannot_read_another_clients_candidates(api_client, db, world):
    headers = external_headers_for(db, world["abc"])
    resp = api_client.get(
        f"/api/talent/external/requests/{world['xyz_req'].id}/candidates", headers=headers
    )
    assert resp.status_code == 404


def test_manipulated_query_client_id_is_ignored(api_client, db, world):
    headers = external_headers_for(db, world["abc"])
    resp = api_client.get(
        "/api/talent/external/requests",
        params={"client_id": world["xyz"].id},
        headers=headers,
    )
    assert resp.status_code == 200
    assert {r["designation"] for r in resp.json()} == {"ABC Role", "ABC Hidden Role"}


# --- client visibility ---------------------------------------------------


def test_only_client_visible_applications_are_returned(api_client, db, world):
    headers = external_headers_for(db, world["abc"])
    visible = api_client.get(
        f"/api/talent/external/requests/{world['abc_req'].id}/candidates", headers=headers
    )
    assert visible.status_code == 200 and len(visible.json()) == 1

    hidden = api_client.get(
        f"/api/talent/external/requests/{world['abc_req_hidden'].id}/candidates", headers=headers
    )
    assert hidden.status_code == 200 and hidden.json() == []


def test_flipping_visibility_off_removes_the_row_on_next_read(api_client, db, world):
    headers = external_headers_for(db, world["abc"])
    app_row = db.execute(
        Application.__table__.select().where(
            Application.talent_request_id == world["abc_req"].id
        )
    ).first()
    api_app = db.get(Application, app_row.id)
    api_app.is_client_visible = False
    db.commit()

    resp = api_client.get(
        f"/api/talent/external/requests/{world['abc_req'].id}/candidates", headers=headers
    )
    assert resp.status_code == 200 and resp.json() == []


# --- signing trust boundary (both directions) --------------------------


def _external_token_for(db, world, **grant_kwargs) -> str:
    from app.services.magic_link_service import MagicLinkService

    grant, _ = make_magic_link_grant(db, world["abc"], **grant_kwargs)
    token, _ = MagicLinkService(db).mint_session_jwt(grant)
    return token


def test_external_session_jwt_is_rejected_on_internal_routes(api_client, db, world):
    token = _external_token_for(db, world)
    headers = {"Authorization": f"Bearer {token}"}
    # Internal routes verify against the internal secret + "dijione-dev-identity"
    # issuer — the external token fails both.
    assert api_client.get("/api/talent/requests", headers=headers).status_code == 401
    assert api_client.get("/api/talent/ta/dashboard", headers=headers).status_code == 401


def test_internal_staff_jwt_is_rejected_on_external_routes(api_client, db, world):
    staff = headers_for(103, full_name="TA User", role="TA_MEMBER")
    assert api_client.get("/api/talent/external/requests", headers=staff).status_code == 401
    assert api_client.get("/api/talent/external/dashboard", headers=staff).status_code == 401


def test_internal_jwt_forged_with_an_external_claim_is_still_rejected(api_client, db, world):
    grant, _ = make_magic_link_grant(db, world["abc"])
    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "sub": str(grant.id),
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "iss": "dijione-dev-identity",  # internal issuer
            "is_active": True,
            "module_roles": {
                "talent-flow": {
                    "role": "TALENT_CLIENT",
                    "client_id": None,
                    "client_ids": None,
                    "permissions": list(EXTERNAL_SESSION_PERMISSIONS),
                }
            },
            "external": {"grant_id": grant.id},
        },
        _INTERNAL_SECRET,  # signed with the INTERNAL secret
        algorithm="HS256",
    )
    resp = api_client.get(
        "/api/talent/external/requests", headers={"Authorization": f"Bearer {forged}"}
    )
    # Fails on the external verifier's secret + issuer, before the grant is
    # ever loaded.
    assert resp.status_code == 401


def test_external_signed_token_without_the_external_claim_is_rejected(api_client, db, world):
    settings = get_settings()
    grant, _ = make_magic_link_grant(db, world["abc"])
    now = datetime.now(UTC)
    no_claim = jwt.encode(
        {
            "sub": str(grant.id),
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "iss": settings.external_session_jwt_issuer,
            "is_active": True,
            "module_roles": {
                "talent-flow": {
                    "role": "TALENT_CLIENT",
                    "client_id": None,
                    "client_ids": None,
                    "permissions": list(EXTERNAL_SESSION_PERMISSIONS),
                }
            },
            # no "external" claim
        },
        settings.external_session_jwt_secret,
        algorithm="HS256",
    )
    resp = api_client.get(
        "/api/talent/external/requests", headers={"Authorization": f"Bearer {no_claim}"}
    )
    assert resp.status_code == 401


# --- rate limiting -------------------------------------------------------


def test_redeem_is_rate_limited_per_source_ip(api_client, db, world):
    _, raw = make_magic_link_grant(db, world["abc"])
    codes = [
        api_client.post("/api/talent/external/redeem", json={"token": raw}).status_code
        for _ in range(13)
    ]
    assert 429 in codes
    assert codes.count(200) <= 10


def test_raw_token_never_appears_in_a_redeem_audit_payload(api_client, db, world, platform_calls):
    _, raw = make_magic_link_grant(db, world["abc"])
    api_client.post("/api/talent/external/redeem", json={"token": raw})
    redeemed = [e for e in platform_calls["audit_events"] if e["action"] == "talent.external.redeemed"]
    assert redeemed
    assert raw not in str(redeemed)
    assert "token_hash" not in str(redeemed[0].get("metadata", {}))


def test_regression_internal_client_persona_routes_unaffected(api_client, db, world):
    """A real internal TALENT_CLIENT persona still reaches the internal
    routes normally — the external path is additive."""
    headers = headers_for(201, full_name="ABC Client", role="TALENT_CLIENT", client_id=world["abc"].id)
    resp = api_client.get("/api/talent/requests", headers=headers)
    assert resp.status_code == 200
    assert {r["designation"] for r in resp.json()} == {"ABC Role", "ABC Hidden Role"}
