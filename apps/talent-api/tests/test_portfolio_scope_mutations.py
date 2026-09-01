"""A portfolio-restricted staff user (TalentScope.client_ids = a subset) must
not be able to READ or MUTATE records outside their assigned clients — the
audit found scope was enforced on reads but not on application/interview
mutations or the TA dashboard aggregates.
"""

from datetime import UTC, datetime, timedelta

from app.models.candidate import Candidate
from app.models.interview import Interview
from app.schemas.application import ApplicationCreate
from app.schemas.talent_request import TalentRequestCreate
from app.services.application_service import ApplicationService
from app.services.talent_request_service import TalentRequestService
from tests.conftest import headers_for


def _seed(db, world):
    """One application + one interview for ABC and one each for XYZ."""
    svc = TalentRequestService(db)
    app_svc = ApplicationService(db)
    out = {}
    for key, client, user in (
        ("abc", world["abc"], world["abc_user_id"]),
        ("xyz", world["xyz"], world["xyz_user_id"]),
    ):
        req = svc.create_request(
            client_id=client.id,
            created_by=user,
            payload=TalentRequestCreate(designation=f"{key} Role", description="d", required_skills=["x"]),
        )
        cand = Candidate(full_name=f"{key} cand", email=f"{key}@example.com")
        db.add(cand)
        db.flush()
        app_row = app_svc.create_application(
            actor_id=world["ta_user_id"],
            payload=ApplicationCreate(candidate_id=cand.id, talent_request_id=req.id),
        )
        db.flush()
        iv = Interview(
            application_id=app_row.id,
            scheduled_at=datetime.now(UTC) + timedelta(days=1),
            interview_type="CLIENT_INTERVIEW",
            status="SCHEDULED",
        )
        db.add(iv)
        db.flush()
        out[key] = {
            "application_id": app_row.id,
            "interview_id": iv.id,
            "request_id": req.id,
            "candidate_id": cand.id,
        }
    db.commit()
    return out


def _portfolio_headers(world):
    # TA member restricted to ABC only (XYZ excluded).
    return headers_for(
        world["ta_user_id"], full_name="Portfolio TA", role="TA_MEMBER", client_ids=[world["abc"].id]
    )


def test_scoped_staff_cannot_read_out_of_portfolio_application(api_client, db, two_tenant_world):
    seeded = _seed(db, two_tenant_world)
    headers = _portfolio_headers(two_tenant_world)

    own = api_client.get("/api/talent/applications", headers=headers)
    ids = {a["id"] for a in own.json()}
    assert seeded["abc"]["application_id"] in ids
    assert seeded["xyz"]["application_id"] not in ids


def test_scoped_staff_cannot_mutate_out_of_portfolio_application(api_client, db, two_tenant_world, platform_calls):
    seeded = _seed(db, two_tenant_world)
    headers = _portfolio_headers(two_tenant_world)
    xyz_app = seeded["xyz"]["application_id"]

    for path, body in (
        (f"/api/talent/applications/{xyz_app}/stage", {"stage": "INTERVIEWS"}),
        (f"/api/talent/applications/{xyz_app}/status", {"status": "SHORTLISTED"}),
        (f"/api/talent/applications/{xyz_app}/score", {"score": 8.0}),
        (f"/api/talent/applications/{xyz_app}/visibility", {"is_client_visible": True}),
    ):
        resp = api_client.patch(path, headers=headers, json=body)
        assert resp.status_code == 404, f"{path} should 404 for an out-of-portfolio staff user"

    # ...but the in-portfolio application is mutable.
    ok = api_client.patch(
        f"/api/talent/applications/{seeded['abc']['application_id']}/stage",
        headers=headers,
        json={"stage": "SCREENING"},
    )
    assert ok.status_code == 200


def test_scoped_staff_cannot_create_application_for_out_of_portfolio_request(
    api_client, db, two_tenant_world
):
    """POST /api/talent/applications takes talent_request_id from the JSON
    body, not a scoped URL path segment like the sibling endpoints — a
    portfolio-restricted staff user must not be able to link a candidate to
    an out-of-portfolio request just by supplying its id."""
    seeded = _seed(db, two_tenant_world)
    headers = _portfolio_headers(two_tenant_world)

    blocked = api_client.post(
        "/api/talent/applications",
        headers=headers,
        json={
            "candidate_id": seeded["abc"]["candidate_id"],
            "talent_request_id": seeded["xyz"]["request_id"],
        },
    )
    assert blocked.status_code == 404

    # In-portfolio creation still works, including linking a candidate who
    # already has an application with a different (out-of-portfolio)
    # client — candidates are shared master records, not client-owned.
    ok = api_client.post(
        "/api/talent/applications",
        headers=headers,
        json={
            "candidate_id": seeded["xyz"]["candidate_id"],
            "talent_request_id": seeded["abc"]["request_id"],
        },
    )
    assert ok.status_code == 201


def test_scoped_staff_cannot_mutate_out_of_portfolio_interview(api_client, db, two_tenant_world, platform_calls):
    seeded = _seed(db, two_tenant_world)
    headers = _portfolio_headers(two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/interviews/{seeded['xyz']['interview_id']}/status",
        headers=headers,
        json={"status": "COMPLETED", "notes": ""},
    )
    assert resp.status_code == 404

    ok = api_client.patch(
        f"/api/talent/interviews/{seeded['abc']['interview_id']}/status",
        headers=headers,
        json={"status": "COMPLETED", "notes": ""},
    )
    assert ok.status_code == 200


def test_ta_dashboard_counts_are_portfolio_scoped(api_client, db, two_tenant_world):
    _seed(db, two_tenant_world)

    unrestricted = api_client.get(
        "/api/talent/ta/dashboard", headers=two_tenant_world["ta_headers"]
    ).json()
    scoped = api_client.get(
        "/api/talent/ta/dashboard", headers=_portfolio_headers(two_tenant_world)
    ).json()

    assert unrestricted["active_applications"] == 2
    assert scoped["active_applications"] == 1
    assert scoped["clients"] == 1


def test_unrestricted_staff_unaffected(api_client, db, two_tenant_world):
    seeded = _seed(db, two_tenant_world)
    # client_ids=None (ALL_CLIENTS) -> can mutate any client's records.
    resp = api_client.patch(
        f"/api/talent/applications/{seeded['xyz']['application_id']}/stage",
        headers=two_tenant_world["ta_headers"],
        json={"stage": "INTERVIEWS"},
    )
    assert resp.status_code == 200
