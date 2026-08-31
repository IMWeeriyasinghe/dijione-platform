"""Fail-closed guarantees for DTC-tag client resolution: only a clean
RESOLVED mapping is ever client-visible; clients can't touch mappings.
"""

import json

from app.models.posting import Posting
from app.models.posting_client_mapping import PostingClientMapping
from app.repositories.posting_repo import PostingRepository
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler


def _seed(db, tags, lever_id):
    p = Posting(lever_posting_id=lever_id, title="T " + lever_id, state="published", tags=json.dumps(tags))
    db.add(p)
    db.flush()
    db.add(PostingClientMapping(posting_id=p.id, status="UNMAPPED"))
    db.flush()
    return p


def test_non_resolved_states_are_never_client_visible(db, two_tenant_world, platform_calls):
    abc = two_tenant_world["abc"]
    _seed(db, [f"DTC - {abc.name}"], "ok")          # -> RESOLVED / VERIFIED
    _seed(db, ["DTC - Crofti"], "unknown")           # -> UNKNOWN
    _seed(db, [f"DTC - {abc.name}", "DTC - X"], "multi")  # -> AMBIGUOUS
    _seed(db, ["DTC -"], "malformed")                # -> MALFORMED
    _seed(db, ["Remote"], "notag")                   # -> NO_DTC_TAG
    PostingClientMappingReconciler(db).reconcile_all()
    db.commit()

    visible = PostingRepository(db).list_verified_for_client(client_id=abc.id)
    assert [p.lever_posting_id for p in visible] == ["ok"]  # only the clean resolution


def test_conflict_manual_override_keeps_only_the_manual_client_visible(db, two_tenant_world, platform_calls):
    abc, xyz = two_tenant_world["abc"], two_tenant_world["xyz"]
    p = _seed(db, [f"DTC - {xyz.name}"], "conflict")
    m = db.query(PostingClientMapping).filter_by(posting_id=p.id).one()
    m.status = "VERIFIED"
    m.client_id = abc.id
    m.source = "MANUAL"
    db.commit()

    PostingClientMappingReconciler(db).reconcile_all()
    db.commit()

    # visible to the MANUALLY-mapped client only; NOT to the DTC-tag client
    assert [p.lever_posting_id for p in PostingRepository(db).list_verified_for_client(client_id=abc.id)] == ["conflict"]
    assert PostingRepository(db).list_verified_for_client(client_id=xyz.id) == []


def test_client_persona_cannot_verify_or_list_staff_postings(api_client, db, two_tenant_world):
    api_client.post("/api/talent/postings/sync", headers=two_tenant_world["ta_headers"])
    pid = api_client.get("/api/talent/postings", headers=two_tenant_world["ta_headers"]).json()[0]["id"]

    assert api_client.get(
        "/api/talent/postings", headers=two_tenant_world["abc_headers"]
    ).status_code == 403
    assert api_client.post(
        f"/api/talent/postings/{pid}/verify-mapping",
        json={"client_id": two_tenant_world["abc"].id},
        headers=two_tenant_world["abc_headers"],
    ).status_code == 403
