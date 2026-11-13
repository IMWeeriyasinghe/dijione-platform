"""Stage 2: Identity Management API — authorization, scoping, validation, audit."""

from datetime import date

import pytest

from app.models.identity import IdentityEvent, IdentityMapping
from app.services import workforce_directory
from tests.conftest import headers_for
from tests.identity_helpers import BASE, EVIDENCE, create, ready

READ_PATHS = [f"{BASE}/unmapped", f"{BASE}/mappings", f"{BASE}/conflicts", f"{BASE}/readiness?site_id=dev-site",
              f"{BASE}/directory/search?q=ab", f"{BASE}/codes/101?site_id=dev-site",
              f"{BASE}/codes/101/evidence?site_id=dev-site&bamboohr_id=1&proposed_from=2026-10-01"]
WRITES = [
    ("post", f"{BASE}/mappings", {"site_id": "dev-site", "zk_emp_code": "101", "bamboohr_id": "1",
                                  "valid_from": "2026-01-01", "evidence": EVIDENCE}),
    ("post", f"{BASE}/mappings/1/close", {"valid_to": "2026-01-02", "reason": "left the company"}),
    ("post", f"{BASE}/mappings/1/correct", {"reason": "wrong employee selected"}),
    ("post", f"{BASE}/codes/101/reassign", {"site_id": "dev-site", "effective_from": "2026-01-02",
                                            "reason": "code reissued by IT", "new": {"bamboohr_id": "2",
                                                                                      "evidence": EVIDENCE}}),
    ("post", f"{BASE}/rejections", {"site_id": "dev-site", "zk_emp_code": "101", "bamboohr_id": "2",
                                    "reason": "not this person per HR"}),
    ("post", f"{BASE}/rejections/1/withdraw", {"reason": "rejection entered in error"}),
]


def test_viewer_cannot_read_or_write(api_client, db, directory, audit_calls):
    ready(api_client)
    for path in READ_PATHS:
        assert api_client.get(path, headers=headers_for("ONSITE_VIEWER")).status_code == 403, path
    for verb, path, body in WRITES:
        assert getattr(api_client, verb)(path, json=body, headers=headers_for("ONSITE_VIEWER")).status_code == 403
    assert api_client.get(f"{BASE}/unmapped").status_code == 401
    assert db.query(IdentityMapping).count() == 0
    assert not [c for c in audit_calls if c.get("entity_type", "").startswith("OnsiteIdentity")]


def test_identity_read_without_manage_cannot_write(api_client, db, directory, audit_calls, monkeypatch):
    from tests import conftest

    monkeypatch.setitem(conftest.PERMS, "ONSITE_ADMIN", [p for p in conftest.ADMIN if p != "onsite.identity.manage"])
    ready(api_client)
    assert api_client.get(f"{BASE}/mappings", headers=headers_for()).status_code == 200
    assert create(api_client, code="101", bid="1", valid_from="2026-01-01").status_code == 403


def test_create_records_history_and_audit(api_client, db, directory, audit_calls):
    ready(api_client)
    resp = create(api_client, code="101", bid="1", valid_from="2026-10-01")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["zk_emp_code"], body["bamboohr_id"], body["status"], body["valid_to"]) == ("101", "1", "VERIFIED", None)
    assert body["employee_name"] == "A" and body["employee_number_snapshot"] == "101"
    ev = db.query(IdentityEvent).filter_by(entity_type="MAPPING", entity_id=body["id"]).all()
    assert [e.action for e in ev] == ["CREATED"] and ev[0].actor_user_id == 1
    assert audit_calls[-1]["entity_type"] == "OnsiteIdentityMapping"
    assert audit_calls[-1]["action"] == "onsite.identity.mapping.created"


@pytest.mark.parametrize("evidence", ["", "short", "         x"])
def test_evidence_is_mandatory(api_client, db, directory, audit_calls, evidence):
    ready(api_client)
    resp = create(api_client, code="101", bid="1", valid_from="2026-10-01", evidence=evidence)
    assert resp.status_code == 422 and resp.json()["detail"]["error"] == "EVIDENCE_REQUIRED"
    assert db.query(IdentityMapping).count() == 0


def test_valid_from_is_never_defaulted(api_client, db, directory, audit_calls):
    ready(api_client)
    resp = api_client.post(f"{BASE}/mappings", headers=headers_for(), json={
        "site_id": "dev-site", "zk_emp_code": "101", "bamboohr_id": "1", "evidence": EVIDENCE})
    assert resp.status_code == 422


def test_warnings_must_be_acknowledged_individually(api_client, db, directory, audit_calls):
    ready(api_client)
    # bamboohr 3 is Inactive (terminated 2025-08-31); code 101 has punches before 2026-10-14.
    first = create(api_client, code="101", bid="3", valid_from="2026-10-14", ack=False)
    assert first.status_code == 422
    codes = set(first.json()["detail"]["unacknowledged"])
    assert {"PRIOR_UNMAPPED_ACTIVITY", "EXTENDS_PAST_TERMINATION", "EMPLOYEE_NOT_ACTIVE"} <= codes
    partial = api_client.post(f"{BASE}/mappings", headers=headers_for(), json={
        "site_id": "dev-site", "zk_emp_code": "101", "bamboohr_id": "3", "valid_from": "2026-10-14",
        "evidence": EVIDENCE, "acknowledged_warnings": sorted(codes)[:1]})
    assert partial.status_code == 422
    assert create(api_client, code="101", bid="3", valid_from="2026-10-14").status_code == 201


def test_overlap_rejected_touching_allowed(api_client, db, directory, audit_calls):
    ready(api_client)
    assert create(api_client, code="101", bid="1", valid_from="2026-01-01", valid_to="2026-06-30").status_code == 201
    clash = create(api_client, code="101", bid="2", valid_from="2026-06-30")
    assert clash.status_code == 409 and clash.json()["detail"]["error"] == "OVERLAPPING_MAPPING"
    assert create(api_client, code="101", bid="2", valid_from="2026-07-01").status_code == 201


def test_unknown_employee_and_directory_unavailable_fail_closed(api_client, db, directory, audit_calls, monkeypatch):
    ready(api_client)
    assert create(api_client, code="101", bid="nope", valid_from="2026-01-01").status_code == 422
    monkeypatch.setattr(workforce_directory, "load",
                        lambda force=False: workforce_directory.DirectorySnapshot(available=False))
    resp = create(api_client, code="101", bid="1", valid_from="2026-01-01")
    assert resp.status_code == 503 and db.query(IdentityMapping).count() == 0


def test_site_scope(api_client, db, directory, audit_calls):
    ready(api_client)  # syd-site exists in the source but is NOT enabled
    assert create(api_client, code="110", bid="10", valid_from="2026-01-01", site="syd-site").status_code == 403
    assert api_client.get(f"{BASE}/readiness?site_id=syd-site", headers=headers_for()).status_code == 403
    assert api_client.get(f"{BASE}/codes/110?site_id=syd-site", headers=headers_for()).status_code == 403


def test_writes_can_be_frozen(api_client, db, directory, audit_calls, monkeypatch):
    from app.core.config import get_settings

    ready(api_client)
    monkeypatch.setattr(get_settings(), "onsite_identity_writes_enabled", False)
    resp = create(api_client, code="101", bid="1", valid_from="2026-01-01")
    assert resp.status_code == 503 and resp.json()["detail"]["error"] == "IDENTITY_WRITES_FROZEN"
    assert api_client.get(f"{BASE}/mappings", headers=headers_for()).status_code == 200


def test_unmapped_report_never_suggests_an_identity(api_client, db, directory, audit_calls):
    ready(api_client)
    rows = api_client.get(f"{BASE}/unmapped?page_size=50", headers=headers_for()).json()["items"]
    by = {r["zk_emp_code"]: r for r in rows}
    assert set(by) == {"101", "102", "0107", "999", "103", "105", "TEST-AZURE-001"}
    assert by["999"]["hint_employee_number_matches"] == []
    hint = by["105"]["hint_employee_number_matches"]  # two directory people share Employee Number 105
    assert {h["bamboohr_id"] for h in hint} == {"5", "6"}
    assert all(h["basis"] == "EMPLOYEE_NUMBER_EQUALS_ID_UNVERIFIED" for h in hint)
    for r in rows:
        assert not any("suggest" in k or "selected" in k for k in r)
    # Rejected candidates are no longer hinted.
    api_client.post(f"{BASE}/rejections", headers=headers_for(), json={
        "site_id": "dev-site", "zk_emp_code": "105", "bamboohr_id": "6", "reason": "HR confirmed not this person"})
    rows = api_client.get(f"{BASE}/unmapped?q=105", headers=headers_for()).json()["items"]
    assert [h["bamboohr_id"] for h in rows[0]["hint_employee_number_matches"]] == ["5"]
    assert rows[0]["rejections"][0]["bamboohr_id"] == "6"
    # Mapped codes leave the outstanding list.
    create(api_client, code="999", bid="2", valid_from="2026-10-01")
    assert "999" not in {r["zk_emp_code"] for r in api_client.get(
        f"{BASE}/unmapped?page_size=50", headers=headers_for()).json()["items"]}
    csv_text = api_client.get(f"{BASE}/unmapped?format=csv", headers=headers_for()).text
    assert csv_text.splitlines()[0].startswith("site_id,zk_emp_code")


def test_directory_search_requires_typed_query(api_client, db, directory, audit_calls):
    ready(api_client)
    assert api_client.get(f"{BASE}/directory/search", headers=headers_for()).status_code == 422
    assert api_client.get(f"{BASE}/directory/search?q=a", headers=headers_for()).status_code == 422
    create(api_client, code="101", bid="1", valid_from="2026-01-01")
    hits = api_client.get(f"{BASE}/directory/search?q=101", headers=headers_for()).json()["items"]
    assert hits[0]["bamboohr_id"] == "1" and hits[0]["active_codes"] == ["101"]


def test_code_investigation_is_admin_only_and_complete(api_client, db, directory, audit_calls):
    ready(api_client)
    create(api_client, code="101", bid="1", valid_from="2026-10-14")
    body = api_client.get(f"{BASE}/codes/101?site_id=dev-site", headers=headers_for()).json()
    assert [(d["local_date"], d["mapping_status"]) for d in body["days"]] == [
        ("2026-10-13", "UNMAPPED"), ("2026-10-14", "MAPPED")]
    assert len(body["mappings"]) == 1


def test_mapping_detail_and_csv(api_client, db, directory, audit_calls):
    ready(api_client)
    mid = create(api_client, code="101", bid="1", valid_from="2026-01-01").json()["id"]
    body = api_client.get(f"{BASE}/mappings/{mid}", headers=headers_for()).json()
    assert body["history"][0]["action"] == "CREATED"
    assert api_client.get(f"{BASE}/mappings/999", headers=headers_for()).status_code == 404
    text = api_client.get(f"{BASE}/mappings?format=csv", headers=headers_for()).text
    assert text.splitlines()[0].startswith("id,site_id,zk_emp_code,bamboohr_id")
    assert date.fromisoformat(body["valid_from"]) == date(2026, 1, 1)
