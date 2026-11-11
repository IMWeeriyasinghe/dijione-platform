"""Regression tests for the client-access findings: withdrawing access when a
mapping changes, unshared candidates in interviews, client-safe portal fields,
client roles with no client, and posting-management scope and audit."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.application import Application
from app.models.document import Document
from app.models.interview import Interview
from app.models.message import Message
from app.models.talent_request import TalentRequest
from app.services.magic_link_service import MagicLinkService
from app.services.recruitment_consumer_service import RecruitmentConsumerService
from tests.conftest import (
    FakeRecruitmentClient,
    headers_for,
    make_magic_link_grant,
    recruitment_candidacy_dto,
    recruitment_posting_dto,
)

REQUESTS = "/api/talent/requests"
EXTERNAL = "/api/talent/external"
FORBIDDEN_PORTAL_FIELDS = {
    "notes", "ta_status", "customer_success_status", "priority", "client_id",
    "client_name", "description", "lifecycle_status",
}


def _reconcile(db, client_name=None, ext="p1", opp="opp-1"):
    tagged = {"dtc_status": "OK", "dtc_client_name": client_name, "dtc_raw_tag": f"DTC - {client_name}"}
    dto = recruitment_posting_dto(ext, **(tagged if client_name else {}))
    candidacy = recruitment_candidacy_dto(opp, posting_external_id=ext, candidate_external_id="c-1")
    source = FakeRecruitmentClient([dto], candidacies=[candidacy])
    result = RecruitmentConsumerService(db, client=source).refresh_projection_and_reconcile()
    db.expire_all()
    return result


def _request(db, client) -> TalentRequest:
    return db.execute(
        select(TalentRequest).where(TalentRequest.client_id == client.id)
    ).scalars().one()


def _share_all(db) -> None:
    for application in db.execute(select(Application)).scalars():
        application.is_client_visible = True
    db.commit()


def _external_headers(db, client) -> dict:
    grant, _ = make_magic_link_grant(db, client)
    token, _ = MagicLinkService(db).mint_session_jwt(grant)
    return {"Authorization": f"Bearer {token}"}


def _ref_id(api_client, world, ext="p1") -> int:
    rows = api_client.get("/api/talent/postings", headers=world["ta_headers"]).json()
    return next(p["id"] for p in rows if p["external_id"] == ext)


@pytest.fixture()
def shared(db, two_tenant_world):
    """A posting verified for ABC, with its one candidate shared."""
    _reconcile(db, two_tenant_world["abc"].name)
    _share_all(db)
    return two_tenant_world


# --- P0-2: withdrawal ------------------------------------------------------


def test_unmap_withdraws_access_on_the_next_read(api_client, db, shared, platform_calls):
    request_id = _request(db, shared["abc"]).id
    external = _external_headers(db, shared["abc"])
    assert api_client.get(f"{EXTERNAL}/requests/{request_id}", headers=external).status_code == 200

    ref_id = _ref_id(api_client, shared)
    api_client.post(f"/api/talent/postings/{ref_id}/unmap-mapping", headers=shared["ta_headers"])

    assert api_client.get(REQUESTS, headers=shared["abc_headers"]).json() == []
    assert api_client.get(f"{REQUESTS}/{request_id}", headers=shared["abc_headers"]).status_code == 404
    assert api_client.get(f"{EXTERNAL}/requests", headers=external).json() == []
    assert api_client.get(f"{EXTERNAL}/requests/{request_id}", headers=external).status_code == 404
    db.expire_all()
    assert db.execute(select(Application)).scalars().one().is_client_visible is False


def test_application_detail_is_withdrawn_with_the_mapping(api_client, db, shared, platform_calls):
    application_id = db.execute(select(Application)).scalars().one().id
    external = _external_headers(db, shared["abc"])
    url = f"{EXTERNAL}/applications/{application_id}"
    assert api_client.get(url, headers=external).status_code == 200

    ref_id = _ref_id(api_client, shared)
    api_client.post(f"/api/talent/postings/{ref_id}/unmap-mapping", headers=shared["ta_headers"])
    assert api_client.get(url, headers=external).status_code == 404


def test_removed_tag_withdraws_access_at_reconcile(api_client, db, shared, platform_calls):
    result = _reconcile(db)

    assert result["promotion"]["requests_access_withdrawn"] == 1
    assert api_client.get(REQUESTS, headers=shared["abc_headers"]).json() == []
    assert db.execute(select(Application)).scalars().one().is_client_visible is False


def test_retag_moves_nothing_and_new_client_starts_unshared(api_client, db, shared, platform_calls):
    old = _request(db, shared["abc"])
    db.add(Message(talent_request_id=old.id, sender_id=1, sender_role="TALENT_CLIENT", body="private"))
    db.commit()
    old_id = old.id

    result = _reconcile(db, shared["xyz"].name)

    assert result["reassigned"] == 1
    assert result["promotion"]["requests_retired"] == 1
    assert api_client.get(REQUESTS, headers=shared["abc_headers"]).json() == []

    new = _request(db, shared["xyz"])
    assert new.id != old_id
    assert [a.is_client_visible for a in new.applications] == [False]
    assert db.execute(
        select(Message).where(Message.talent_request_id == new.id)
    ).scalars().all() == []
    assert db.get(TalentRequest, old_id).lifecycle_status == "CANCELLED"

    xyz_external = _external_headers(db, shared["xyz"])
    assert api_client.get(f"{REQUESTS}/{old_id}", headers=shared["xyz_headers"]).status_code == 404
    url = f"{EXTERNAL}/requests/{new.id}/candidates"
    assert api_client.get(url, headers=xyz_external).json() == []


def test_retag_is_idempotent_and_can_return_to_the_first_client(db, shared, platform_calls):
    _reconcile(db, shared["xyz"].name)
    assert _reconcile(db, shared["xyz"].name)["promotion"]["requests_retired"] == 0

    assert _reconcile(db, shared["abc"].name)["promotion"]["requests_retired"] == 1
    live = db.execute(select(TalentRequest).where(TalentRequest.provider == "LEVER")).scalars().one()
    assert live.client_id == shared["abc"].id
    assert [a.is_client_visible for a in live.applications] == [False]


def test_manual_verify_to_another_client_withdraws_immediately(api_client, db, shared, platform_calls):
    ref_id = _ref_id(api_client, shared)
    resp = api_client.post(
        f"/api/talent/postings/{ref_id}/verify-mapping",
        json={"client_id": shared["xyz"].id},
        headers=shared["ta_headers"],
    )

    assert resp.status_code == 200
    assert api_client.get(REQUESTS, headers=shared["abc_headers"]).json() == []
    assert api_client.get(REQUESTS, headers=shared["xyz_headers"]).json() == []


def test_reverify_for_same_client_does_not_reshare(api_client, db, shared, platform_calls):
    ref_id = _ref_id(api_client, shared)
    api_client.post(f"/api/talent/postings/{ref_id}/unmap-mapping", headers=shared["ta_headers"])
    api_client.post(
        f"/api/talent/postings/{ref_id}/verify-mapping",
        json={"client_id": shared["abc"].id},
        headers=shared["ta_headers"],
    )

    assert len(api_client.get(REQUESTS, headers=shared["abc_headers"]).json()) == 1
    db.expire_all()
    assert db.execute(select(Application)).scalars().one().is_client_visible is False


def test_conflicting_tag_keeps_manual_client_access(api_client, db, shared, platform_calls):
    ref_id = _ref_id(api_client, shared)
    api_client.post(
        f"/api/talent/postings/{ref_id}/verify-mapping",
        json={"client_id": shared["abc"].id},
        headers=shared["ta_headers"],
    )

    result = _reconcile(db, shared["xyz"].name)

    assert result["conflicts"] == 1 and result["promotion"]["requests_retired"] == 0
    assert len(api_client.get(REQUESTS, headers=shared["abc_headers"]).json()) == 1


# --- P0-3: interviews ------------------------------------------------------


def _interview(db) -> None:
    application = db.execute(select(Application)).scalars().one()
    db.add(Interview(application_id=application.id, scheduled_at=datetime.now(UTC) + timedelta(days=1)))
    db.commit()


def test_interview_of_unshared_candidate_is_hidden(api_client, db, two_tenant_world):
    _reconcile(db, two_tenant_world["abc"].name)
    _interview(db)
    external = _external_headers(db, two_tenant_world["abc"])

    assert api_client.get("/api/talent/interviews", headers=two_tenant_world["abc_headers"]).json() == []
    assert api_client.get(f"{EXTERNAL}/interviews", headers=external).json() == []
    assert api_client.get(f"{EXTERNAL}/dashboard", headers=external).json()["interviews_this_week"] == 0


def test_interview_of_shared_candidate_is_visible_only_to_its_client(api_client, db, shared):
    _interview(db)

    assert len(api_client.get(f"{EXTERNAL}/interviews", headers=_external_headers(db, shared["abc"])).json()) == 1
    assert api_client.get(f"{EXTERNAL}/interviews", headers=_external_headers(db, shared["xyz"])).json() == []
    assert api_client.get("/api/talent/interviews", headers=shared["xyz_headers"]).json() == []


def test_staff_still_see_interviews_of_unshared_candidates(api_client, db, two_tenant_world):
    _reconcile(db, two_tenant_world["abc"].name)
    _interview(db)

    assert len(api_client.get("/api/talent/interviews", headers=two_tenant_world["ta_headers"]).json()) == 1


# --- P0-4: portal fields ---------------------------------------------------


def test_portal_responses_expose_only_client_safe_fields(api_client, db, shared):
    request = _request(db, shared["abc"])
    request.notes = "internal note"
    db.commit()
    external = _external_headers(db, shared["abc"])

    listed = api_client.get(f"{EXTERNAL}/requests", headers=external).json()[0]
    detail = api_client.get(f"{EXTERNAL}/requests/{request.id}", headers=external)
    dashboard = api_client.get(f"{EXTERNAL}/dashboard", headers=external).json()["requests"][0]

    for body in (listed, detail.json(), dashboard):
        assert not FORBIDDEN_PORTAL_FIELDS & set(body)
    assert "internal note" not in detail.text


def test_portal_counts_only_shared_candidates(api_client, db, two_tenant_world):
    _reconcile(db, two_tenant_world["abc"].name)
    external = _external_headers(db, two_tenant_world["abc"])

    assert api_client.get(f"{EXTERNAL}/requests", headers=external).json()[0]["active_application_count"] == 0
    assert api_client.get(f"{EXTERNAL}/dashboard", headers=external).json()["candidates_in_process"] == 0

    _share_all(db)
    assert api_client.get(f"{EXTERNAL}/requests", headers=external).json()[0]["active_application_count"] == 1
    assert api_client.get(f"{EXTERNAL}/dashboard", headers=external).json()["candidates_in_process"] == 1


# --- P0-6: client role with no client --------------------------------------


@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"client_ids": [1, 2]},
        {"client_public_id": "cli-does-not-exist"},
        {"client_public_ids": ["cli-abc-company"]},
    ],
)
@pytest.mark.parametrize(
    "url", [REQUESTS, "/api/talent/interviews", "/api/talent/postings/client-visible"]
)
def test_client_role_without_a_resolved_client_is_refused(api_client, db, shared, scope, url):
    headers = headers_for(150, role="TALENT_CLIENT", **scope)
    assert api_client.get(url, headers=headers).status_code == 403


def test_staff_without_a_client_keep_access(api_client, shared):
    assert len(api_client.get(REQUESTS, headers=shared["ta_headers"]).json()) == 1


# --- P1-4: posting management ----------------------------------------------


@pytest.fixture()
def restricted(db, two_tenant_world):
    """A posting held by ABC, one held by nobody, and XYZ-only staff."""
    _reconcile(db, two_tenant_world["abc"].name)
    _reconcile_extra = recruitment_posting_dto("free")
    RecruitmentConsumerService(
        db,
        client=FakeRecruitmentClient([
            recruitment_posting_dto(
                "p1", dtc_status="OK", dtc_client_name=two_tenant_world["abc"].name,
                dtc_raw_tag="DTC - ABC Company",
            ),
            _reconcile_extra,
        ]),
    ).refresh_projection_and_reconcile()
    return {**two_tenant_world, "xyz_staff": headers_for(160, role="TA_MEMBER", client_ids=[two_tenant_world["xyz"].id])}


def test_restricted_staff_cannot_see_another_clients_posting(api_client, restricted):
    rows = api_client.get("/api/talent/postings", headers=restricted["xyz_staff"]).json()
    assert [p["external_id"] for p in rows] == ["free"]
    ref_id = _ref_id(api_client, restricted)
    assert api_client.get(f"/api/talent/postings/{ref_id}", headers=restricted["xyz_staff"]).status_code == 404


@pytest.mark.parametrize("action", ["unmap-mapping", "reopen-mapping"])
def test_restricted_staff_cannot_change_another_clients_posting(api_client, db, restricted, action):
    ref_id = _ref_id(api_client, restricted)
    url = f"/api/talent/postings/{ref_id}/{action}"
    assert api_client.post(url, headers=restricted["xyz_staff"]).status_code == 404
    assert len(api_client.get(REQUESTS, headers=restricted["abc_headers"]).json()) == 1


def test_restricted_staff_cannot_verify_onto_or_away_from_other_clients(api_client, restricted):
    held = _ref_id(api_client, restricted)
    free = _ref_id(api_client, restricted, "free")
    url = "/api/talent/postings/{}/verify-mapping"

    outside = api_client.post(
        url.format(free), json={"client_id": restricted["abc"].id}, headers=restricted["xyz_staff"]
    )
    taken = api_client.post(
        url.format(held), json={"client_id": restricted["xyz"].id}, headers=restricted["xyz_staff"]
    )
    assert outside.status_code == 404 and taken.status_code == 404


def test_restricted_staff_can_verify_a_free_posting_for_their_client(api_client, restricted):
    free = _ref_id(api_client, restricted, "free")
    resp = api_client.post(
        f"/api/talent/postings/{free}/verify-mapping",
        json={"client_id": restricted["xyz"].id},
        headers=restricted["xyz_staff"],
    )
    assert resp.status_code == 200


def test_restricted_staff_cannot_overturn_a_rejection(api_client, restricted):
    held = _ref_id(api_client, restricted)
    api_client.post(f"/api/talent/postings/{held}/unmap-mapping", headers=restricted["ta_headers"])

    reopen = api_client.post(f"/api/talent/postings/{held}/reopen-mapping", headers=restricted["xyz_staff"])
    verify = api_client.post(
        f"/api/talent/postings/{held}/verify-mapping",
        json={"client_id": restricted["xyz"].id},
        headers=restricted["xyz_staff"],
    )
    assert reopen.status_code == 404 and verify.status_code == 404


def test_manual_verify_is_audited(api_client, two_tenant_world, db, platform_calls):
    _reconcile(db)
    ref_id = _ref_id(api_client, two_tenant_world)

    api_client.post(
        f"/api/talent/postings/{ref_id}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["ta_headers"],
    )

    event = next(
        c for c in platform_calls["audit_events"] if c["action"] == "posting_mapping.manually_verified"
    )
    assert event["new_state"]["client_id"] == two_tenant_world["abc"].id


# --- withdrawal across every client surface --------------------------------


def _add_history(db, request) -> None:
    db.add(Message(talent_request_id=request.id, sender_id=1, sender_role="TALENT_CLIENT", body="private"))
    db.add(Document(talent_request_id=request.id, file_name="old.pdf", uploaded_by=1, storage_reference="x"))
    db.commit()


def test_unmap_closes_messages_documents_and_dashboard(api_client, db, shared, platform_calls):
    request = _request(db, shared["abc"])
    _add_history(db, request)
    _interview(db)
    urls = [f"{REQUESTS}/{request.id}/messages", f"{REQUESTS}/{request.id}/documents"]
    for url in urls:
        assert api_client.get(url, headers=shared["abc_headers"]).status_code == 200

    ref_id = _ref_id(api_client, shared)
    api_client.post(f"/api/talent/postings/{ref_id}/unmap-mapping", headers=shared["ta_headers"])

    for url in urls:
        assert api_client.get(url, headers=shared["abc_headers"]).status_code == 404
    assert api_client.post(urls[0], json={"body": "hi"}, headers=shared["abc_headers"]).status_code == 404
    assert api_client.get("/api/talent/interviews", headers=shared["abc_headers"]).json() == []
    dashboard = api_client.get("/api/talent/dashboard/client", headers=shared["abc_headers"]).json()
    assert dashboard["requests"] == [] and dashboard["candidates_in_process"] == 0


def test_session_issued_before_retag_loses_the_request_and_keeps_only_valid_scope(api_client, db, shared, platform_calls):
    request_id = _request(db, shared["abc"]).id
    application_id = db.execute(select(Application)).scalars().one().id
    _interview(db)
    external = _external_headers(db, shared["abc"])

    _reconcile(db, shared["xyz"].name)

    assert api_client.get(f"{EXTERNAL}/requests/{request_id}", headers=external).status_code == 404
    assert api_client.get(f"{EXTERNAL}/requests/{request_id}/candidates", headers=external).status_code == 404
    assert api_client.get(f"{EXTERNAL}/applications/{application_id}", headers=external).status_code == 404
    assert api_client.get(f"{EXTERNAL}/interviews", headers=external).json() == []
    dashboard = api_client.get(f"{EXTERNAL}/dashboard", headers=external)
    assert dashboard.status_code == 200 and dashboard.json()["requests"] == []


def test_new_client_sees_no_history_on_any_surface(api_client, db, shared, platform_calls):
    old = _request(db, shared["abc"])
    _add_history(db, old)
    old_application = db.execute(select(Application)).scalars().one().id
    _interview(db)
    old_id = old.id

    _reconcile(db, shared["xyz"].name)
    new = _request(db, shared["xyz"])
    headers = shared["xyz_headers"]
    external = _external_headers(db, shared["xyz"])

    assert api_client.get(f"{REQUESTS}/{new.id}/messages", headers=headers).json() == []
    assert api_client.get(f"{REQUESTS}/{new.id}/documents", headers=headers).json() == []
    assert api_client.get("/api/talent/interviews", headers=headers).json() == []
    assert api_client.get(f"{EXTERNAL}/interviews", headers=external).json() == []
    assert api_client.get(f"{EXTERNAL}/dashboard", headers=external).json()["candidates_in_process"] == 0
    for url in (f"{REQUESTS}/{old_id}/messages", f"{REQUESTS}/{old_id}/documents"):
        assert api_client.get(url, headers=headers).status_code == 404
    assert api_client.get(f"{EXTERNAL}/applications/{old_application}", headers=external).status_code == 404


def test_old_client_loses_candidate_lists_and_new_client_cannot_read_the_retired_request(api_client, db, shared, platform_calls):
    old_id = _request(db, shared["abc"]).id
    url = f"{REQUESTS}/{old_id}/candidates"
    assert api_client.get(url, headers=shared["abc_headers"]).status_code == 200

    _reconcile(db, shared["xyz"].name)

    assert api_client.get(url, headers=shared["abc_headers"]).status_code == 404
    assert api_client.get(url, headers=shared["xyz_headers"]).status_code == 404
    new_id = _request(db, shared["xyz"]).id
    assert api_client.get(f"{REQUESTS}/{new_id}/candidates", headers=shared["xyz_headers"]).json() == []
    assert api_client.get(f"{REQUESTS}/{new_id}", headers=shared["abc_headers"]).status_code == 404
