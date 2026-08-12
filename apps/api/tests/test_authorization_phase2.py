"""DijiOne Phase 2 authorization coverage (CR §34, §53):

- staff client/portfolio scope (selected clients vs. ALL_CLIENTS)
- disabled module assignment removes access
- disabled user cannot authenticate
- permission-gated review action
"""

from app.core.constants import MODULE_TALENT_FLOW, TalentFlowRole
from app.models.client import Client
from app.models.user import User, UserModuleRole
from app.schemas.talent_request import TalentRequestCreate
from app.services.talent_request_service import TalentRequestService
from tests.conftest import assign_client_scope, auth_headers


def _three_client_world(db):
    abc = Client(name="ABC Company", industry="Financial Services", status="ACTIVE")
    xyz = Client(name="XYZ Company", industry="Retail", status="ACTIVE")
    nova = Client(name="Nova Solutions", industry="Technology", status="ACTIVE")
    db.add_all([abc, xyz, nova])
    db.flush()

    portfolio_ta = User(
        email="portfolio-ta@example.com", full_name="Portfolio TA", platform_role="PLATFORM_USER",
        persona_key="test-portfolio-ta",
    )
    all_clients_ta = User(
        email="all-ta@example.com", full_name="All Clients TA", platform_role="PLATFORM_USER",
        persona_key="test-all-ta",
    )
    db.add_all([portfolio_ta, all_clients_ta])
    db.flush()

    portfolio_role = UserModuleRole(
        user_id=portfolio_ta.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.TA_MEMBER.value
    )
    all_role = UserModuleRole(
        user_id=all_clients_ta.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.TA_MEMBER.value
    )
    db.add_all([portfolio_role, all_role])
    db.flush()

    assign_client_scope(db, portfolio_role, client_id=abc.id)
    assign_client_scope(db, portfolio_role, client_id=xyz.id)
    assign_client_scope(db, all_role, client_id=None)  # ALL_CLIENTS

    service = TalentRequestService(db)
    abc_req = service.create_request(
        client_id=abc.id, created_by=portfolio_ta.id,
        payload=TalentRequestCreate(designation="ABC Role", description="d", required_skills=["x"]),
    )
    xyz_req = service.create_request(
        client_id=xyz.id, created_by=portfolio_ta.id,
        payload=TalentRequestCreate(designation="XYZ Role", description="d", required_skills=["x"]),
    )
    nova_req = service.create_request(
        client_id=nova.id, created_by=portfolio_ta.id,
        payload=TalentRequestCreate(designation="Nova Role", description="d", required_skills=["x"]),
    )
    db.commit()
    return {"abc": abc, "xyz": xyz, "nova": nova, "abc_req": abc_req, "xyz_req": xyz_req, "nova_req": nova_req}


def test_portfolio_ta_cannot_read_unassigned_client(api_client, db):
    world = _three_client_world(db)
    headers = auth_headers(api_client, "test-portfolio-ta")

    resp = api_client.get("/api/talent/requests", headers=headers)
    ids = {r["id"] for r in resp.json()}
    assert world["abc_req"].id in ids
    assert world["xyz_req"].id in ids
    assert world["nova_req"].id not in ids

    resp = api_client.get(f"/api/talent/requests/{world['nova_req'].id}", headers=headers)
    assert resp.status_code == 404

    resp = api_client.get("/api/talent/clients", headers=headers)
    names = {c["name"] for c in resp.json()}
    assert names == {"ABC Company", "XYZ Company"}


def test_all_clients_ta_sees_everything(api_client, db):
    world = _three_client_world(db)
    headers = auth_headers(api_client, "test-all-ta")

    resp = api_client.get("/api/talent/requests", headers=headers)
    ids = {r["id"] for r in resp.json()}
    assert {world["abc_req"].id, world["xyz_req"].id, world["nova_req"].id} <= ids

    resp = api_client.get(f"/api/talent/requests/{world['nova_req'].id}", headers=headers)
    assert resp.status_code == 200


def test_portfolio_ta_cannot_change_stage_of_unassigned_client_request(api_client, db):
    world = _three_client_world(db)
    headers = auth_headers(api_client, "test-portfolio-ta")

    resp = api_client.post(
        f"/api/talent/requests/{world['nova_req'].id}/stage",
        json={"stage": "SOURCING"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_ta_member_cannot_review_without_permission(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-ta")
    service = TalentRequestService(db)
    req = service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user"].id,
        payload=TalentRequestCreate(designation="Role", description="d", required_skills=["x"]),
    )
    db.commit()

    resp = api_client.post(
        f"/api/talent/requests/{req.id}/review", json={"decision": "APPROVED", "reason": ""}, headers=headers
    )
    assert resp.status_code == 403


def test_customer_success_can_review(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-cs")
    service = TalentRequestService(db)
    req = service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user"].id,
        payload=TalentRequestCreate(designation="Role", description="d", required_skills=["x"]),
    )
    db.commit()

    resp = api_client.post(
        f"/api/talent/requests/{req.id}/review", json={"decision": "APPROVED", "reason": "ok"}, headers=headers
    )
    assert resp.status_code == 200


def test_disabled_module_assignment_blocks_access(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-ta")
    resp = api_client.get("/api/talent/ta/dashboard", headers=headers)
    assert resp.status_code == 200

    from sqlalchemy import select

    from app.models.user import UserModuleRole as UMR

    role = db.execute(
        select(UMR).where(UMR.user_id == two_tenant_world["ta_user"].id)
    ).scalars().first()
    role.enabled = False
    db.commit()

    resp = api_client.get("/api/talent/ta/dashboard", headers=headers)
    assert resp.status_code == 403


def test_disabled_user_cannot_login(api_client, db, two_tenant_world):
    two_tenant_world["ta_user"].is_active = False
    db.commit()

    resp = api_client.post("/api/auth/dev-login", json={"persona_key": "test-ta"})
    assert resp.status_code == 403
