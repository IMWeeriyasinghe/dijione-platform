"""Fail-closed Posting -> Client visibility (CLAUDE.md §60): a client user
must never see a Posting, mapped or not, unless its PostingClientMapping
is VERIFIED for that exact client_id. Tag/title text must never be used
as authorization evidence — only the explicit staff verify-mapping action.
"""

from app.core.constants import PostingClientMappingStatus


def test_sync_creates_unmapped_postings(api_client, db, two_tenant_world):
    resp = api_client.post("/api/talent/postings/sync", headers=two_tenant_world["ta_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 3  # MockLeverClient's 3 fixture postings
    assert body["updated"] == 0

    staff_list = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"])
    assert staff_list.status_code == 200
    postings = staff_list.json()
    assert len(postings) == 3
    assert all(p["mapping_status"] == PostingClientMappingStatus.UNMAPPED.value for p in postings)
    assert all(p["mapping_client_id"] is None for p in postings)


def test_unmapped_posting_invisible_to_every_client(api_client, db, two_tenant_world):
    api_client.post("/api/talent/postings/sync", headers=two_tenant_world["ta_headers"])

    abc_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["abc_headers"]
    )
    xyz_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["xyz_headers"]
    )
    assert abc_view.status_code == 200
    assert xyz_view.status_code == 200
    assert abc_view.json() == []
    assert xyz_view.json() == []


def test_verified_posting_visible_only_to_its_own_client(api_client, db, two_tenant_world):
    api_client.post("/api/talent/postings/sync", headers=two_tenant_world["ta_headers"])
    postings = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()
    target_posting_id = postings[0]["id"]

    verify_resp = api_client.post(
        f"/api/talent/postings/{target_posting_id}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["ta_headers"],
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["mapping_status"] == PostingClientMappingStatus.VERIFIED.value
    assert verify_resp.json()["mapping_client_id"] == two_tenant_world["abc"].id
    assert verify_resp.json()["mapping_source"] == "MANUAL"

    abc_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["abc_headers"]
    ).json()
    assert len(abc_view) == 1
    assert abc_view[0]["id"] == target_posting_id
    # Client-safe DTO must never leak tags/team/department/mapping internals.
    assert "tags" not in abc_view[0]
    assert "team" not in abc_view[0]
    assert "mapping_status" not in abc_view[0]

    # A second client must never see it, even though it's now verified.
    xyz_view = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["xyz_headers"]
    ).json()
    assert xyz_view == []


def test_staff_unresolved_filter_excludes_verified_postings(api_client, db, two_tenant_world):
    api_client.post("/api/talent/postings/sync", headers=two_tenant_world["ta_headers"])
    postings = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()
    verified_id = postings[0]["id"]
    api_client.post(
        f"/api/talent/postings/{verified_id}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["ta_headers"],
    )

    unresolved = api_client.get(
        "/api/talent/postings", params={"unresolved_only": True}, headers=two_tenant_world["ta_headers"]
    ).json()
    assert len(unresolved) == 2
    assert verified_id not in {p["id"] for p in unresolved}

    all_staff = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()
    assert len(all_staff) == 3  # staff still sees the verified one too


def test_client_role_cannot_reach_staff_posting_routes(api_client, db, two_tenant_world):
    resp = api_client.get("/api/talent/postings", headers=two_tenant_world["abc_headers"])
    assert resp.status_code == 403

    sync_resp = api_client.post(
        "/api/talent/postings/sync", headers=two_tenant_world["abc_headers"]
    )
    assert sync_resp.status_code == 403


def test_staff_calling_client_visible_route_sees_nothing(api_client, db, two_tenant_world):
    api_client.post("/api/talent/postings/sync", headers=two_tenant_world["ta_headers"])
    resp = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["ta_headers"]
    )
    assert resp.status_code == 200
    assert resp.json() == []
