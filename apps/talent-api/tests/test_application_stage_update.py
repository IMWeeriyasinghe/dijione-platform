"""Regression coverage for PATCH /api/talent/applications/{id}/stage.

This endpoint was previously always 422: the schema field was `current_stage`,
the handler read `payload.stage`, and the frontend sent `{stage}`. Canonical
field is now `stage` everywhere. See docs/talent-flow/authorization-review.md.
"""

from app.models.candidate import Candidate
from app.schemas.application import ApplicationCreate
from app.schemas.talent_request import TalentRequestCreate
from app.services.application_service import ApplicationService
from app.services.talent_request_service import TalentRequestService


def _seed_application(db, world):
    request = TalentRequestService(db).create_request(
        client_id=world["abc"].id,
        created_by=world["abc_user_id"],
        payload=TalentRequestCreate(designation="ABC Role", description="d", required_skills=["x"]),
    )
    candidate = Candidate(full_name="Ron Axel", email="ron@example.com")
    db.add(candidate)
    db.flush()
    app_row = ApplicationService(db).create_application(
        actor_id=world["ta_user_id"],
        payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=request.id),
    )
    db.commit()
    return app_row.id


def test_stage_update_succeeds_and_is_audited(api_client, db, two_tenant_world, platform_calls):
    app_id = _seed_application(db, two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/applications/{app_id}/stage",
        headers=two_tenant_world["ta_headers"],
        json={"stage": "INTERVIEWS"},
    )

    assert resp.status_code == 200
    assert resp.json()["current_stage"] == "INTERVIEWS"
    actions = [c["action"] for c in platform_calls["audit_events"]]
    assert "application.stage_changed" in actions


def test_stage_update_rejects_unknown_stage(api_client, db, two_tenant_world):
    app_id = _seed_application(db, two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/applications/{app_id}/stage",
        headers=two_tenant_world["ta_headers"],
        json={"stage": "NOT_A_REAL_STAGE"},
    )

    assert resp.status_code == 400


def test_stage_update_missing_field_is_422(api_client, db, two_tenant_world):
    app_id = _seed_application(db, two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/applications/{app_id}/stage",
        headers=two_tenant_world["ta_headers"],
        json={"current_stage": "INTERVIEWS"},  # the old, wrong field name
    )

    assert resp.status_code == 422


def test_stage_update_unknown_application_is_404(api_client, db, two_tenant_world):
    resp = api_client.patch(
        "/api/talent/applications/999999/stage",
        headers=two_tenant_world["ta_headers"],
        json={"stage": "INTERVIEWS"},
    )

    assert resp.status_code == 404
