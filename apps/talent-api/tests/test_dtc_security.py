"""Fail-closed guarantees for DTC-tag client resolution: only a clean
RESOLVED mapping is ever client-visible; clients can't touch mappings.
"""

from app.models.recruitment_posting_ref import RecruitmentPostingRef
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.repositories.posting_repo import PostingRepository
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler
from tests.conftest import recruitment_posting_dto


def _dtc_ok(name, ext):
    return recruitment_posting_dto(ext, dtc_status="OK", dtc_client_name=name, dtc_raw_tag=f"DTC - {name}")


def test_non_resolved_states_are_never_client_visible(db, two_tenant_world, platform_calls):
    abc = two_tenant_world["abc"]
    dtos = [
        _dtc_ok(abc.name, "ok"),
        _dtc_ok("Crofti", "unknown"),
        recruitment_posting_dto("multi", dtc_status="MULTIPLE",
                                dtc_raw_tags=[f"DTC - {abc.name}", "DTC - X"]),
        recruitment_posting_dto("malformed", dtc_status="MALFORMED", dtc_raw_tag="DTC -"),
        recruitment_posting_dto("notag", dtc_status="NO_TAG"),
    ]
    PostingClientMappingReconciler(db).reconcile_postings(dtos)
    db.commit()

    visible = PostingRepository(db).list_verified_for_client(client_id=abc.id)
    assert [r.external_id for r in visible] == ["ok"]


def test_conflict_manual_override_keeps_only_the_manual_client_visible(db, two_tenant_world, platform_calls):
    abc, xyz = two_tenant_world["abc"], two_tenant_world["xyz"]
    db.add(RecruitmentPostingRef(provider="LEVER", external_id="conflict", title="C"))
    db.commit()
    m = PostingClientMappingRepository(db).get_or_create("conflict")
    m.status, m.client_id, m.source = "VERIFIED", abc.id, "MANUAL"
    db.commit()

    PostingClientMappingReconciler(db).reconcile_postings([_dtc_ok(xyz.name, "conflict")])
    db.commit()

    assert [r.external_id for r in PostingRepository(db).list_verified_for_client(client_id=abc.id)] == ["conflict"]
    assert PostingRepository(db).list_verified_for_client(client_id=xyz.id) == []


def test_client_persona_cannot_verify_or_list_staff_postings(api_client, db, two_tenant_world):
    db.add(RecruitmentPostingRef(provider="LEVER", external_id="p1", title="T"))
    db.commit()
    ref_id = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()[0]["id"]

    assert api_client.get(
        "/api/talent/postings", headers=two_tenant_world["abc_headers"]
    ).status_code == 403
    assert api_client.post(
        f"/api/talent/postings/{ref_id}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["abc_headers"],
    ).status_code == 403
