"""GET /api/talent/external/applications/{application_id} — Candidate
Review Detail, the client-safe single-candidate view behind a clickable
card on the external request-detail page.

Fail-closed 4-part invariant (plan §K4/§23): a valid external session AND
a server-resolved grant client AND the application's own request belongs
to that exact client AND is_client_visible == True — anything else is an
identical 404, no existence leak. The response reuses
CandidateService.to_client_safe_out, the same DTO already proven leak-free
for the candidates-list endpoint (no email/phone/score/notes/provider ids/
other-client data).
"""

from __future__ import annotations

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.talent_request import TalentRequest
from tests.conftest import external_headers_for


def _make_world(db):
    from app.models.client import Client

    abc = Client(name="ABC Company", platform_client_id="cli-abc-company", status="ACTIVE")
    xyz = Client(name="XYZ Company", platform_client_id="cli-xyz-company", status="ACTIVE")
    db.add_all([abc, xyz])
    db.commit()

    def _application(client, designation, *, visible: bool) -> Application:
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
            full_name=f"Cand {designation}", email="cand@example.com", phone="+94-000",
            professional_title="Engineer", summary="", skills="Python,SQL",
            source="LEVER", availability_status="IN_PROCESS",
        )
        db.add(cand)
        db.flush()
        app_row = Application(
            candidate_id=cand.id, talent_request_id=tr.id, current_stage="SOURCING",
            status="ACTIVE", is_client_visible=visible,
            recruiter_notes="Confidential internal recruiter note.",
            lever_opportunity_id=f"opp-secret-{tr.id}",
        )
        db.add(app_row)
        db.commit()
        return app_row

    return {
        "abc": abc,
        "xyz": xyz,
        "abc_visible": _application(abc, "ABC Role", visible=True),
        "abc_hidden": _application(abc, "ABC Hidden Role", visible=False),
        "xyz_visible": _application(xyz, "XYZ Role", visible=True),
    }


def test_client_visible_application_is_returned_client_safe(api_client, db):
    world = _make_world(db)
    headers = external_headers_for(db, world["abc"])

    resp = api_client.get(
        f"/api/talent/external/applications/{world['abc_visible'].id}", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["application_id"] == world["abc_visible"].id
    assert body["full_name"] == "Cand ABC Role"
    assert body["professional_title"] == "Engineer"
    assert body["current_stage"] == "SOURCING"

    # Structural DTO leak check — no field name here has ever meant email,
    # phone, score, internal notes, or a provider id.
    leaked_keys = {"email", "phone", "score", "recruiter_notes", "lever_opportunity_id"}
    assert not (leaked_keys & body.keys())
    assert "@" not in resp.text  # no email anywhere in the payload
    assert "opp-secret" not in resp.text
    assert "Confidential internal recruiter note." not in resp.text


def test_non_visible_application_is_404(api_client, db):
    world = _make_world(db)
    headers = external_headers_for(db, world["abc"])

    resp = api_client.get(
        f"/api/talent/external/applications/{world['abc_hidden'].id}", headers=headers
    )
    assert resp.status_code == 404


def test_cross_client_application_is_404_no_leak(api_client, db):
    world = _make_world(db)
    headers = external_headers_for(db, world["abc"])

    resp = api_client.get(
        f"/api/talent/external/applications/{world['xyz_visible'].id}", headers=headers
    )
    assert resp.status_code == 404
    assert "XYZ" not in resp.text


def test_unknown_application_is_404(api_client, db):
    world = _make_world(db)
    headers = external_headers_for(db, world["abc"])

    resp = api_client.get("/api/talent/external/applications/999999", headers=headers)
    assert resp.status_code == 404


def test_requires_a_valid_external_session(api_client, db):
    world = _make_world(db)
    resp = api_client.get(f"/api/talent/external/applications/{world['abc_visible'].id}")
    assert resp.status_code in (401, 403)


def test_visibility_flip_off_locks_out_an_already_seen_candidate(api_client, db):
    world = _make_world(db)
    headers = external_headers_for(db, world["abc"])

    ok = api_client.get(
        f"/api/talent/external/applications/{world['abc_visible'].id}", headers=headers
    )
    assert ok.status_code == 200

    world["abc_visible"].is_client_visible = False
    db.commit()

    now_hidden = api_client.get(
        f"/api/talent/external/applications/{world['abc_visible'].id}", headers=headers
    )
    assert now_hidden.status_code == 404
