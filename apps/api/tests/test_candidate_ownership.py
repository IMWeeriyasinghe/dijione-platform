"""Candidate Ownership Rule (CLAUDE.md §19): one candidate can have
applications against multiple clients without ever being duplicated, and a
client must only ever see the client-safe view of their own application —
never the candidate's applications with other clients or internal notes."""

import pytest

from app.schemas.application import ApplicationCreate
from app.schemas.candidate import CandidateCreate
from app.schemas.talent_request import TalentRequestCreate
from app.services.application_service import ApplicationService, DuplicateApplicationError
from app.services.candidate_service import CandidateService
from app.services.talent_request_service import TalentRequestService
from tests.conftest import auth_headers


def test_candidate_can_apply_to_two_clients_as_one_master_record(db, two_tenant_world):
    request_service = TalentRequestService(db)
    abc_request = request_service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user"].id,
        payload=TalentRequestCreate(designation="Role A", description="d", required_skills=[]),
    )
    xyz_request = request_service.create_request(
        client_id=two_tenant_world["xyz"].id, created_by=two_tenant_world["xyz_user"].id,
        payload=TalentRequestCreate(designation="Role B", description="d", required_skills=[]),
    )

    candidate_service = CandidateService(db)
    candidate = candidate_service.create_candidate(
        CandidateCreate(full_name="Shared Candidate", email="shared-candidate@example.com")
    )

    application_service = ApplicationService(db)
    application_service.create_application(
        actor_id=two_tenant_world["ta_user"].id,
        payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=abc_request.id),
    )
    application_service.create_application(
        actor_id=two_tenant_world["ta_user"].id,
        payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=xyz_request.id),
    )
    db.commit()

    out = candidate_service.to_out(candidate)
    assert len(out.applications) == 2
    client_names = {a.client_name for a in out.applications}
    assert client_names == {"ABC Company", "XYZ Company"}


def test_duplicate_application_for_same_pair_is_rejected(db, two_tenant_world):
    request_service = TalentRequestService(db)
    request = request_service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user"].id,
        payload=TalentRequestCreate(designation="Role", description="d", required_skills=[]),
    )
    candidate_service = CandidateService(db)
    candidate = candidate_service.create_candidate(
        CandidateCreate(full_name="Solo Candidate", email="solo-candidate@example.com")
    )
    application_service = ApplicationService(db)
    application_service.create_application(
        actor_id=two_tenant_world["ta_user"].id,
        payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=request.id),
    )
    db.commit()

    with pytest.raises(DuplicateApplicationError):
        application_service.create_application(
            actor_id=two_tenant_world["ta_user"].id,
            payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=request.id),
        )


def test_client_safe_view_hides_internal_fields_and_other_client_applications(
    api_client, db, two_tenant_world
):
    request_service = TalentRequestService(db)
    abc_request = request_service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user"].id,
        payload=TalentRequestCreate(designation="Role A", description="d", required_skills=[]),
    )
    xyz_request = request_service.create_request(
        client_id=two_tenant_world["xyz"].id, created_by=two_tenant_world["xyz_user"].id,
        payload=TalentRequestCreate(designation="Role B", description="d", required_skills=[]),
    )
    candidate_service = CandidateService(db)
    candidate = candidate_service.create_candidate(
        CandidateCreate(full_name="Cross Client Candidate", email="cross-client@example.com")
    )
    application_service = ApplicationService(db)
    abc_app = application_service.create_application(
        actor_id=two_tenant_world["ta_user"].id,
        payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=abc_request.id),
    )
    application_service.create_application(
        actor_id=two_tenant_world["ta_user"].id,
        payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=xyz_request.id),
    )
    application_service.update_score(
        application_id=abc_app.id, actor_id=two_tenant_world["ta_user"].id,
        score=9.5, recruiter_notes="Confidential internal recruiter note.",
    )
    application_service.update_visibility(
        application_id=abc_app.id, actor_id=two_tenant_world["ta_user"].id,
        is_client_visible=True, client_visible_notes="Great fit for the ABC role.",
    )
    db.commit()

    headers = auth_headers(api_client, "test-abc-client")
    resp = api_client.get(f"/api/talent/requests/{abc_request.id}/candidates", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    candidate_view = payload[0]

    assert "score" not in candidate_view
    assert "recruiter_notes" not in candidate_view
    assert "applications" not in candidate_view
    assert candidate_view["full_name"] == "Cross Client Candidate"
