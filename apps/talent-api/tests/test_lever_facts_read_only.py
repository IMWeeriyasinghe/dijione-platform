"""Regression coverage for PATCH /api/talent/applications/{id}/{stage,status,score,visibility}.

DijiTalentFlow monitoring-first iteration: recruitment stage and status are
Lever facts, refreshed from the Recruitment Source on every reconcile, so a
manual edit here would be silently reverted — the endpoints are retired
(403), same convention as `POST /api/talent/requests` / `POST
/api/talent/candidates`. Candidate scoring has no authoritative source at
all and is fully retired. `is_client_visible` is the one field TalentFlow
still owns and lets a TA edit.

(Formerly test_application_stage_update.py — renamed to reflect what the
route now does.)
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


def test_stage_update_is_retired(api_client, db, two_tenant_world):
    app_id = _seed_application(db, two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/applications/{app_id}/stage",
        headers=two_tenant_world["ta_headers"],
        json={"stage": "INTERVIEWS"},
    )

    assert resp.status_code == 403


def test_status_update_is_retired(api_client, db, two_tenant_world):
    app_id = _seed_application(db, two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/applications/{app_id}/status",
        headers=two_tenant_world["ta_headers"],
        json={"status": "SHORTLISTED", "rejection_reason": ""},
    )

    assert resp.status_code == 403


def test_score_update_is_retired(api_client, db, two_tenant_world):
    app_id = _seed_application(db, two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/applications/{app_id}/score",
        headers=two_tenant_world["ta_headers"],
        json={"score": 8.5, "recruiter_notes": "Strong candidate."},
    )

    assert resp.status_code == 403


def test_visibility_update_still_succeeds(api_client, db, two_tenant_world, platform_calls):
    app_id = _seed_application(db, two_tenant_world)

    resp = api_client.patch(
        f"/api/talent/applications/{app_id}/visibility",
        headers=two_tenant_world["ta_headers"],
        json={"is_client_visible": True, "client_visible_notes": "Great fit."},
    )

    assert resp.status_code == 200
    assert resp.json()["is_client_visible"] is True
    actions = [c["action"] for c in platform_calls["audit_events"]]
    assert "application.visibility_changed" in actions


def test_retired_routes_404_for_unknown_application_too(api_client, db, two_tenant_world):
    # Retirement is unconditional — it doesn't even reach the lookup, so an
    # unknown application id still gets the same 403, not a 404.
    resp = api_client.patch(
        "/api/talent/applications/999999/stage",
        headers=two_tenant_world["ta_headers"],
        json={"stage": "INTERVIEWS"},
    )

    assert resp.status_code == 403
