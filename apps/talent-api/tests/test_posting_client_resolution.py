"""Fail-closed posting -> client visibility (CLAUDE.md §60): a client user
must never see a posting unless its PostingClientMapping is VERIFIED for
that exact client_id. The posting projection and the trust record are both
local tables — this decision never depends on recruitment-api.
"""

from app.core.constants import PostingClientMappingStatus
from app.models.recruitment_posting_ref import RecruitmentPostingRef
from app.services.recruitment_consumer_service import RecruitmentConsumerService
from tests.conftest import FakeRecruitmentClient, recruitment_posting_dto

_VERIFIED = PostingClientMappingStatus.VERIFIED.value
_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value


def _seed_refs(db, *externals: str) -> None:
    for ext in externals:
        db.add(RecruitmentPostingRef(provider="LEVER", external_id=ext, title=f"Role {ext}"))
    db.commit()


def test_projection_refresh_creates_unmapped_mappings(api_client, db, two_tenant_world):
    dtos = [recruitment_posting_dto("p1"), recruitment_posting_dto("p2"), recruitment_posting_dto("p3")]
    RecruitmentConsumerService(db, client=FakeRecruitmentClient(dtos)).refresh_projection_and_reconcile()

    staff = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"])
    assert staff.status_code == 200
    postings = staff.json()
    assert len(postings) == 3
    assert all(p["mapping_status"] == _UNMAPPED for p in postings)
    assert all(p["mapping_client_id"] is None for p in postings)


def test_unmapped_posting_invisible_to_every_client(api_client, db, two_tenant_world):
    _seed_refs(db, "p1", "p2")
    for hdr in ("abc_headers", "xyz_headers"):
        resp = api_client.get("/api/talent/postings/client-visible", headers=two_tenant_world[hdr])
        assert resp.status_code == 200
        assert resp.json() == []


def test_verified_posting_visible_only_to_its_own_client(api_client, db, two_tenant_world):
    _seed_refs(db, "p1", "p2", "p3")
    refs = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()
    target = refs[0]

    verify = api_client.post(
        f"/api/talent/postings/{target['id']}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["ta_headers"],
    )
    assert verify.status_code == 200
    assert verify.json()["mapping_status"] == _VERIFIED
    assert verify.json()["mapping_source"] == "MANUAL"

    abc_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["abc_headers"]
    ).json()
    assert [p["id"] for p in abc_view] == [target["id"]]
    assert "tags" not in abc_view[0] and "mapping_status" not in abc_view[0]

    xyz_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["xyz_headers"]
    ).json()
    assert xyz_view == []


def test_unresolved_filter_excludes_verified(api_client, db, two_tenant_world):
    _seed_refs(db, "p1", "p2", "p3")
    refs = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()
    api_client.post(
        f"/api/talent/postings/{refs[0]['id']}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["ta_headers"],
    )
    unresolved = api_client.get(
        "/api/talent/postings", params={"unresolved_only": True}, headers=two_tenant_world["ta_headers"]
    ).json()
    assert len(unresolved) == 2
    assert refs[0]["id"] not in {p["id"] for p in unresolved}


def test_client_role_cannot_reach_staff_posting_routes(api_client, db, two_tenant_world):
    assert api_client.get("/api/talent/postings", headers=two_tenant_world["abc_headers"]).status_code == 403
    assert api_client.post(
        "/api/talent/integrations/recruitment/sync", headers=two_tenant_world["abc_headers"]
    ).status_code == 403


def test_recruitment_api_down_does_not_break_client_workspace(api_client, db, two_tenant_world):
    """Failure injection: recruitment-api unavailable. The client workspace
    still loads from the last-good local projection, with no cross-client
    leakage, no visibility widening, and no 500."""
    _seed_refs(db, "p1", "p2")
    # one posting is VERIFIED for ABC in the local trust record
    refs = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()
    api_client.post(
        f"/api/talent/postings/{refs[0]['id']}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["ta_headers"],
    )

    # recruitment-api is DOWN — a refresh is a safe no-op
    svc = RecruitmentConsumerService(db, client=FakeRecruitmentClient(down=True))
    result = svc.refresh_projection_and_reconcile()
    assert result == {"refreshed": False, "reason": "source_unavailable"}
    assert svc.freshness()["available"] is False

    # client visibility still works from the local projection + trust record
    abc_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["abc_headers"]
    )
    assert abc_view.status_code == 200
    assert [p["id"] for p in abc_view.json()] == [refs[0]["id"]]

    xyz_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["xyz_headers"]
    )
    assert xyz_view.status_code == 200
    assert xyz_view.json() == []
