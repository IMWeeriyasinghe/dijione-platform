"""PostingClientMappingReconciler — governed DTC tag fact -> trust mapping.

The reconciler consumes recruitment-api's canonical posting DTO (the DTC
tag is already parsed into a fact). Fail closed on every non-happy path;
never overwrite a human MANUAL VERIFIED mapping; never auto-create a
Client; idempotent.
"""

from app.core.constants import DtcResolutionStatus, PostingClientMappingSource, PostingClientMappingStatus
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler
from tests.conftest import recruitment_posting_dto

V = PostingClientMappingStatus.VERIFIED.value
U = PostingClientMappingStatus.UNMAPPED.value
R = PostingClientMappingStatus.REJECTED.value
DTC = PostingClientMappingSource.LEVER_DTC_TAG.value
MANUAL = PostingClientMappingSource.MANUAL.value


def _reconcile(db, dtos):
    s = PostingClientMappingReconciler(db).reconcile_postings(dtos)
    db.commit()
    return s


def _mapping(db, external_id="p1"):
    return PostingClientMappingRepository(db).get_for_posting(external_id)


def _dtc_ok(name, ext="p1"):
    return recruitment_posting_dto(ext, dtc_status="OK", dtc_client_name=name, dtc_raw_tag=f"DTC - {name}")


def test_unique_match_sets_verified_via_dtc(db, two_tenant_world, platform_calls):
    name = two_tenant_world["abc"].name
    s = _reconcile(db, [_dtc_ok(name)])
    m = _mapping(db)
    assert s.resolved == 1
    assert m.status == V and m.client_id == two_tenant_world["abc"].id and m.source == DTC
    assert m.resolution_status == DtcResolutionStatus.RESOLVED.value
    assert m.dtc_source_tag == f"DTC - {name}"
    assert m.verified_at is not None


def test_unknown_client_stays_unmapped_and_never_creates_client(db, two_tenant_world, platform_calls):
    from app.models.client import Client

    before = db.query(Client).count()
    s = _reconcile(db, [_dtc_ok("Crofti")])
    m = _mapping(db)
    assert s.unknown == 1
    assert m.status == U and m.client_id is None
    assert m.resolution_status == DtcResolutionStatus.UNKNOWN_CLIENT_IDENTIFIER.value
    assert m.dtc_source_tag == "DTC - Crofti"
    assert db.query(Client).count() == before


def test_multiple_dtc_tags_are_ambiguous(db, two_tenant_world, platform_calls):
    dto = recruitment_posting_dto(
        "p1", dtc_status="MULTIPLE",
        dtc_raw_tags=[f"DTC - {two_tenant_world['abc'].name}", "DTC - Crofti"],
    )
    s = _reconcile(db, [dto])
    assert s.ambiguous == 1
    assert _mapping(db).status == U
    assert _mapping(db).resolution_status == DtcResolutionStatus.AMBIGUOUS_MULTIPLE_TAGS.value


def test_malformed_tag_stays_unmapped(db, two_tenant_world, platform_calls):
    s = _reconcile(db, [recruitment_posting_dto("p1", dtc_status="MALFORMED", dtc_raw_tag="DTC -")])
    assert s.malformed == 1
    assert _mapping(db).resolution_status == DtcResolutionStatus.MALFORMED_TAG.value


def test_no_tag_is_no_op(db, two_tenant_world, platform_calls):
    s = _reconcile(db, [recruitment_posting_dto("p1", dtc_status="NO_TAG")])
    assert s.no_tag == 1
    assert _mapping(db).resolution_status == DtcResolutionStatus.NO_DTC_TAG.value


def test_dtc_tag_removed_reverts_previously_resolved_mapping(db, two_tenant_world, platform_calls):
    name = two_tenant_world["abc"].name
    _reconcile(db, [_dtc_ok(name)])
    assert _mapping(db).status == V

    s = _reconcile(db, [recruitment_posting_dto("p1", dtc_status="NO_TAG")])
    m = _mapping(db)
    assert s.reverted == 1
    assert m.status == U and m.client_id is None and m.source == ""
    assert m.resolution_status == DtcResolutionStatus.NO_DTC_TAG.value


def test_dtc_tag_changed_repoints_client(db, two_tenant_world, platform_calls):
    _reconcile(db, [_dtc_ok(two_tenant_world["abc"].name)])
    assert _mapping(db).client_id == two_tenant_world["abc"].id

    s = _reconcile(db, [_dtc_ok(two_tenant_world["xyz"].name)])
    m = _mapping(db)
    assert s.reassigned == 1
    assert m.status == V and m.client_id == two_tenant_world["xyz"].id and m.source == DTC


def test_manual_mapping_that_agrees_is_untouched(db, two_tenant_world, platform_calls):
    _reconcile(db, [recruitment_posting_dto("p1", dtc_status="NO_TAG")])
    m = _mapping(db)
    m.status, m.client_id, m.source, m.verified_by_user_id = V, two_tenant_world["abc"].id, MANUAL, 999
    db.commit()

    s = _reconcile(db, [_dtc_ok(two_tenant_world["abc"].name)])
    m = _mapping(db)
    assert s.unchanged == 1
    assert m.source == MANUAL and m.verified_by_user_id == 999
    assert m.resolution_status == DtcResolutionStatus.RESOLVED.value


def test_manual_mapping_that_conflicts_is_kept_and_flagged(db, two_tenant_world, platform_calls):
    _reconcile(db, [recruitment_posting_dto("p1", dtc_status="NO_TAG")])
    m = _mapping(db)
    m.status, m.client_id, m.source = V, two_tenant_world["abc"].id, MANUAL
    db.commit()

    s = _reconcile(db, [_dtc_ok(two_tenant_world["xyz"].name)])
    m = _mapping(db)
    assert s.conflicts == 1
    assert m.status == V and m.client_id == two_tenant_world["abc"].id and m.source == MANUAL
    assert m.resolution_status == DtcResolutionStatus.CONFLICT_MANUAL_OVERRIDE.value
    assert any(b.get("role") == "TA_MANAGER" for b in platform_calls["broadcasts"])


def test_rejected_mapping_is_never_un_rejected(db, two_tenant_world, platform_calls):
    _reconcile(db, [recruitment_posting_dto("p1", dtc_status="NO_TAG")])
    m = _mapping(db)
    m.status = R
    db.commit()
    _reconcile(db, [_dtc_ok(two_tenant_world["abc"].name)])
    assert _mapping(db).status == R


def test_reconciliation_is_idempotent(db, two_tenant_world, platform_calls):
    dto = _dtc_ok(two_tenant_world["abc"].name)
    first = _reconcile(db, [dto])
    second = _reconcile(db, [dto])
    assert first.resolved == 1
    assert second.resolved == 0 and second.reassigned == 0 and second.reverted == 0
    assert second.unchanged == 1
