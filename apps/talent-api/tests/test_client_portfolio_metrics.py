"""GET /api/talent/clients — the Client Portfolios card metrics extension
(plan §E): active_application_count, client_visible_count,
latest_request_at, alongside the pre-existing total/active request counts.
Also covers GET /api/talent/dashboard/client's new client_name field.
"""

from app.models.application import Application
from app.models.candidate import Candidate
from app.schemas.talent_request import TalentRequestCreate
from app.services.talent_request_service import TalentRequestService


def _seed_request(db, client_id: int, designation: str):
    tr = TalentRequestService(db).create_request(
        client_id=client_id, created_by=999,
        payload=TalentRequestCreate(designation=designation, description="d", required_skills=["x"]),
    )
    db.commit()
    return tr


def _seed_application(db, request, *, status: str, visible: bool) -> Application:
    cand = Candidate(full_name=f"Cand {request.id}-{status}", email=None)
    db.add(cand)
    db.flush()
    app_row = Application(
        candidate_id=cand.id, talent_request_id=request.id, current_stage="SOURCING",
        status=status, is_client_visible=visible,
    )
    db.add(app_row)
    db.commit()
    return app_row


def test_portfolio_metrics_reflect_applications_and_visibility(api_client, db, two_tenant_world):
    abc_id = two_tenant_world["abc"].id
    tr1 = _seed_request(db, abc_id, "ABC Role 1")
    _seed_request(db, abc_id, "ABC Role 2")

    _seed_application(db, tr1, status="SHORTLISTED", visible=True)  # active + visible
    _seed_application(db, tr1, status="WITHDRAWN", visible=True)  # not active, but visible
    _seed_application(db, tr1, status="SHORTLISTED", visible=False)  # active, not visible

    resp = api_client.get("/api/talent/clients", headers=two_tenant_world["ta_headers"])
    assert resp.status_code == 200
    abc_row = next(c for c in resp.json() if c["id"] == abc_id)

    assert abc_row["total_requests"] == 2
    assert abc_row["active_application_count"] == 2  # 2x SHORTLISTED
    assert abc_row["client_visible_count"] == 2  # the two is_client_visible=True rows
    assert abc_row["latest_request_at"] is not None


def test_portfolio_metrics_are_zero_for_a_client_with_no_activity(api_client, db, two_tenant_world):
    resp = api_client.get("/api/talent/clients", headers=two_tenant_world["ta_headers"])
    xyz_row = next(c for c in resp.json() if c["id"] == two_tenant_world["xyz"].id)
    assert xyz_row["total_requests"] == 0
    assert xyz_row["active_application_count"] == 0
    assert xyz_row["client_visible_count"] == 0
    assert xyz_row["latest_request_at"] is None


def test_portfolio_metrics_are_isolated_per_client(api_client, db, two_tenant_world):
    abc_tr = _seed_request(db, two_tenant_world["abc"].id, "ABC Role")
    _seed_application(db, abc_tr, status="SHORTLISTED", visible=True)

    resp = api_client.get("/api/talent/clients", headers=two_tenant_world["ta_headers"])
    by_id = {c["id"]: c for c in resp.json()}
    assert by_id[two_tenant_world["abc"].id]["active_application_count"] == 1
    assert by_id[two_tenant_world["xyz"].id]["active_application_count"] == 0


def test_client_dashboard_includes_client_name(api_client, db, two_tenant_world):
    resp = api_client.get("/api/talent/dashboard/client", headers=two_tenant_world["abc_headers"])
    assert resp.status_code == 200
    assert resp.json()["client_name"] == "ABC Company"
