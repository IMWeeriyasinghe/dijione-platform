"""POST /api/talent/postings/{id}/unmap-mapping + /reopen-mapping.

"Manually Unmapped" is implemented as the existing REJECTED/MANUAL mapping
state, which `PostingClientMappingReconciler` already treats as absolute —
never touched again by a Lever DTC tag change. That's what makes an unmap
actually stick instead of being silently re-VERIFIED by the next 6-hour
reconcile. Reopen returns the mapping to plain UNMAPPED so DTC (or a fresh
manual verify) can resolve it again.
"""

from app.core.constants import DtcResolutionStatus, PostingClientMappingStatus
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler
from app.services.recruitment_consumer_service import RecruitmentConsumerService
from tests.conftest import FakeRecruitmentClient, recruitment_posting_dto

_VERIFIED = PostingClientMappingStatus.VERIFIED.value
_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value
_REJECTED = PostingClientMappingStatus.REJECTED.value


def _seed_verified(db, world, name=None, ext="p1"):
    dto = recruitment_posting_dto(
        ext, dtc_status="OK", dtc_client_name=name or world["abc"].name,
        dtc_raw_tag=f"DTC - {name or world['abc'].name}",
    )
    RecruitmentConsumerService(db, client=FakeRecruitmentClient([dto])).refresh_projection_and_reconcile()


def _ref_id(api_client, world, ext="p1"):
    rows = api_client.get("/api/talent/postings", headers=world["ta_headers"]).json()
    return next(p["id"] for p in rows if p["external_id"] == ext)


def test_unmap_sets_rejected_manual_and_clears_client(api_client, db, two_tenant_world, platform_calls):
    _seed_verified(db, two_tenant_world)
    ref_id = _ref_id(api_client, two_tenant_world)

    resp = api_client.post(
        f"/api/talent/postings/{ref_id}/unmap-mapping", headers=two_tenant_world["ta_headers"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mapping_status"] == _REJECTED
    assert body["mapping_source"] == "MANUAL"
    assert body["mapping_client_id"] is None
    assert body["resolution_status"] == DtcResolutionStatus.MANUALLY_UNMAPPED.value

    actions = [c["action"] for c in platform_calls["audit_events"]]
    assert "posting_mapping.manually_unmapped" in actions


def test_unmap_immediately_drops_client_visibility(api_client, db, two_tenant_world):
    _seed_verified(db, two_tenant_world)
    ref_id = _ref_id(api_client, two_tenant_world)
    before = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["abc_headers"]
    ).json()
    assert len(before) == 1

    api_client.post(f"/api/talent/postings/{ref_id}/unmap-mapping", headers=two_tenant_world["ta_headers"])

    after = api_client.get(
        "/api/talent/postings/client-visible", headers=two_tenant_world["abc_headers"]
    ).json()
    assert after == []


def test_unmapped_mapping_survives_a_reconcile_with_the_dtc_tag_still_present(
    db, two_tenant_world, platform_calls
):
    """The regression this feature exists to fix: a naive reset to plain
    UNMAPPED would be re-VERIFIED by the very next reconcile as long as the
    Lever posting still carries the resolving DTC tag. REJECTED must not
    be."""
    name = two_tenant_world["abc"].name
    _seed_verified(db, two_tenant_world, name=name)

    from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository

    mapping = PostingClientMappingRepository(db).get_for_posting("p1")
    mapping.status = _REJECTED
    mapping.source = "MANUAL"
    mapping.client_id = None
    db.commit()

    # Same DTC-tagged posting comes back on the next sync — reconciler must
    # leave the REJECTED mapping untouched (early-return branch).
    dto = recruitment_posting_dto("p1", dtc_status="OK", dtc_client_name=name, dtc_raw_tag=f"DTC - {name}")
    summary = PostingClientMappingReconciler(db).reconcile_postings([dto])
    db.commit()

    mapping = PostingClientMappingRepository(db).get_for_posting("p1")
    assert mapping.status == _REJECTED
    assert mapping.client_id is None
    assert summary.resolved == 0
    assert summary.reassigned == 0


def test_reopen_returns_to_unmapped_and_next_reconcile_resolves_it(api_client, db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _seed_verified(db, two_tenant_world, name=name)
    ref_id = _ref_id(api_client, two_tenant_world)
    api_client.post(f"/api/talent/postings/{ref_id}/unmap-mapping", headers=two_tenant_world["ta_headers"])

    resp = api_client.post(
        f"/api/talent/postings/{ref_id}/reopen-mapping", headers=two_tenant_world["ta_headers"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mapping_status"] == _UNMAPPED
    assert body["mapping_source"] == ""
    assert body["mapping_client_id"] is None

    # A fresh reconcile with the DTC tag still present now re-resolves it.
    dto = recruitment_posting_dto("p1", dtc_status="OK", dtc_client_name=name, dtc_raw_tag=f"DTC - {name}")
    summary = PostingClientMappingReconciler(db).reconcile_postings([dto])
    db.commit()
    assert summary.resolved == 1

    from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository

    mapping = PostingClientMappingRepository(db).get_for_posting("p1")
    assert mapping.status == _VERIFIED
    assert mapping.client_id == two_tenant_world["abc"].id


def test_unmap_and_reopen_require_staff_scope(api_client, db, two_tenant_world):
    _seed_verified(db, two_tenant_world)
    ref_id = _ref_id(api_client, two_tenant_world)

    unmap = api_client.post(
        f"/api/talent/postings/{ref_id}/unmap-mapping", headers=two_tenant_world["abc_headers"]
    )
    assert unmap.status_code in (401, 403)

    reopen = api_client.post(
        f"/api/talent/postings/{ref_id}/reopen-mapping", headers=two_tenant_world["abc_headers"]
    )
    assert reopen.status_code in (401, 403)


def test_unmap_unknown_posting_is_404(api_client, two_tenant_world):
    resp = api_client.post(
        "/api/talent/postings/999999/unmap-mapping", headers=two_tenant_world["ta_headers"]
    )
    assert resp.status_code == 404
