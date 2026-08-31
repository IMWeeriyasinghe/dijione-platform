"""PostingClientMappingReconciler — governed DTC tag -> trust mapping.

Fail closed on every non-happy path; never overwrite a human MANUAL
VERIFIED mapping; never auto-create a Client; idempotent.
"""

import json

from app.core.constants import DtcResolutionStatus, PostingClientMappingSource, PostingClientMappingStatus
from app.models.posting import Posting
from app.models.posting_client_mapping import PostingClientMapping
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler

V = PostingClientMappingStatus.VERIFIED.value
U = PostingClientMappingStatus.UNMAPPED.value
R = PostingClientMappingStatus.REJECTED.value
DTC = PostingClientMappingSource.LEVER_DTC_TAG.value
MANUAL = PostingClientMappingSource.MANUAL.value


def _posting(db, tags, *, lever_id="p1", title="AI Solutions Engineer"):
    p = Posting(lever_posting_id=lever_id, title=title, state="published", tags=json.dumps(tags))
    db.add(p)
    db.flush()
    m = PostingClientMapping(posting_id=p.id, status=U)
    db.add(m)
    db.flush()
    return p, m


def _reconcile(db):
    s = PostingClientMappingReconciler(db).reconcile_all()
    db.commit()
    return s


def test_unique_match_sets_verified_via_dtc(db, two_tenant_world, platform_calls):
    _p, m = _posting(db, [f"DTC - {two_tenant_world['abc'].name}"])
    s = _reconcile(db)
    db.refresh(m)
    assert s.resolved == 1
    assert m.status == V
    assert m.client_id == two_tenant_world["abc"].id
    assert m.source == DTC
    assert m.resolution_status == DtcResolutionStatus.RESOLVED.value
    assert m.dtc_source_tag == f"DTC - {two_tenant_world['abc'].name}"
    assert m.verified_at is not None


def test_unknown_client_stays_unmapped_and_never_creates_client(db, two_tenant_world, platform_calls):
    from app.models.client import Client

    before = db.query(Client).count()
    _p, m = _posting(db, ["DTC - Crofti"])
    s = _reconcile(db)
    db.refresh(m)
    assert s.unknown == 1
    assert m.status == U and m.client_id is None
    assert m.resolution_status == DtcResolutionStatus.UNKNOWN_CLIENT_IDENTIFIER.value
    assert m.dtc_source_tag == "DTC - Crofti"  # recorded for staff visibility
    assert db.query(Client).count() == before  # no auto-create


def test_multiple_dtc_tags_are_ambiguous(db, two_tenant_world, platform_calls):
    _p, m = _posting(db, [f"DTC - {two_tenant_world['abc'].name}", "DTC - Crofti"])
    s = _reconcile(db)
    db.refresh(m)
    assert s.ambiguous == 1
    assert m.status == U
    assert m.resolution_status == DtcResolutionStatus.AMBIGUOUS_MULTIPLE_TAGS.value


def test_malformed_tag_stays_unmapped(db, two_tenant_world, platform_calls):
    _p, m = _posting(db, ["DTC -"])
    s = _reconcile(db)
    db.refresh(m)
    assert s.malformed == 1
    assert m.status == U
    assert m.resolution_status == DtcResolutionStatus.MALFORMED_TAG.value


def test_no_tag_is_no_op(db, two_tenant_world, platform_calls):
    _p, m = _posting(db, ["Remote", "Full Time"])
    s = _reconcile(db)
    db.refresh(m)
    assert s.no_tag == 1
    assert m.status == U
    assert m.resolution_status == DtcResolutionStatus.NO_DTC_TAG.value


def test_dtc_tag_removed_reverts_previously_resolved_mapping(db, two_tenant_world, platform_calls):
    p, m = _posting(db, [f"DTC - {two_tenant_world['abc'].name}"])
    _reconcile(db)
    db.refresh(m)
    assert m.status == V

    p.tags = json.dumps(["Remote"])  # tag removed in Lever
    db.commit()
    s = _reconcile(db)
    db.refresh(m)
    assert s.reverted == 1
    assert m.status == U and m.client_id is None and m.source == ""
    assert m.resolution_status == DtcResolutionStatus.NO_DTC_TAG.value


def test_dtc_tag_changed_repoints_client(db, two_tenant_world, platform_calls):
    p, m = _posting(db, [f"DTC - {two_tenant_world['abc'].name}"])
    _reconcile(db)
    db.refresh(m)
    assert m.client_id == two_tenant_world["abc"].id

    p.tags = json.dumps([f"DTC - {two_tenant_world['xyz'].name}"])
    db.commit()
    s = _reconcile(db)
    db.refresh(m)
    assert s.reassigned == 1
    assert m.status == V and m.client_id == two_tenant_world["xyz"].id and m.source == DTC


def test_manual_mapping_that_agrees_is_untouched(db, two_tenant_world, platform_calls):
    p, m = _posting(db, [f"DTC - {two_tenant_world['abc'].name}"])
    m.status = V
    m.client_id = two_tenant_world["abc"].id
    m.source = MANUAL
    m.verified_by_user_id = 999
    db.commit()

    s = _reconcile(db)
    db.refresh(m)
    assert s.unchanged == 1
    assert m.source == MANUAL and m.verified_by_user_id == 999  # not overwritten
    assert m.resolution_status == DtcResolutionStatus.RESOLVED.value


def test_manual_mapping_that_conflicts_is_kept_and_flagged(db, two_tenant_world, platform_calls):
    p, m = _posting(db, [f"DTC - {two_tenant_world['xyz'].name}"])
    m.status = V
    m.client_id = two_tenant_world["abc"].id  # human said ABC
    m.source = MANUAL
    db.commit()

    s = _reconcile(db)
    db.refresh(m)
    assert s.conflicts == 1
    assert m.status == V and m.client_id == two_tenant_world["abc"].id and m.source == MANUAL
    assert m.resolution_status == DtcResolutionStatus.CONFLICT_MANUAL_OVERRIDE.value
    # TA_MANAGER notification broadcast
    assert any(
        b.get("role") == "TA_MANAGER" for b in platform_calls["broadcasts"]
    )


def test_rejected_mapping_is_never_un_rejected(db, two_tenant_world, platform_calls):
    p, m = _posting(db, [f"DTC - {two_tenant_world['abc'].name}"])
    m.status = R
    db.commit()
    _reconcile(db)
    db.refresh(m)
    assert m.status == R


def test_reconciliation_is_idempotent(db, two_tenant_world, platform_calls):
    _p, m = _posting(db, [f"DTC - {two_tenant_world['abc'].name}"])
    first = _reconcile(db)
    second = _reconcile(db)
    assert first.resolved == 1
    assert second.resolved == 0 and second.reassigned == 0 and second.reverted == 0
    assert second.unchanged == 1
