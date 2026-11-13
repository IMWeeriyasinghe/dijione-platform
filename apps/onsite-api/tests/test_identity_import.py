"""Stage 2: CSV import — approved format only, mandatory dry-run, per-row
evidence, atomic all-or-nothing apply."""

import time

import pytest

from app.models.identity import IdentityEvent, IdentityMapping
from app.services import identity_import_service as imp
from tests.conftest import headers_for
from tests.identity_helpers import BASE, ready

HEADER = "site_id,zk_emp_code,bamboohr_id,valid_from,valid_to,evidence,verified_by,verified_on,source_reference\n"
ROW_101 = "dev-site,101,1,2026-10-01,,Enrolment sheet signed by HR,HR Officer,2026-11-01,HR-REF-001\n"
ROW_102 = "dev-site,102,2,2026-10-01,,Enrolment sheet signed by HR,HR Officer,2026-11-01,HR-REF-002\n"


def _post(api_client, content: bytes, *, dry_run=True, token=None, ack=False):
    data = {"acknowledge_warnings": str(ack).lower()}
    if token:
        data["dry_run_token"] = token
    return api_client.post(f"{BASE}/import?dry_run={str(dry_run).lower()}", headers=headers_for(),
                           files={"file": ("m.csv", content, "text/csv")}, data=data)


def test_only_the_approved_format_is_accepted(api_client, db, directory, audit_calls):
    ready(api_client)
    workbook_like = b"NOS.,Preferred Name,Access Given/ Not Given,Duplicate ID,done\n12,Someone,Given,45,yes\n"
    resp = _post(api_client, workbook_like)
    assert resp.status_code == 422 and resp.json()["detail"]["error"] == "INVALID_HEADER"


@pytest.mark.parametrize("row,error", [
    ("dev-site,101,1,2026-10-01,,short,HR Officer,2026-11-01,HR-REF-1\n", "EVIDENCE_REQUIRED"),
    ("dev-site,101,1,2026-10-01,,Enrolment sheet signed by HR,,2026-11-01,HR-REF-1\n", "VERIFIED_BY_REQUIRED"),
    ("dev-site,101,1,2026-10-01,,Enrolment sheet signed by HR,HR Officer,,HR-REF-1\n", "VERIFIED_ON_REQUIRED"),
    ("dev-site,101,1,2026-10-01,,Enrolment sheet signed by HR,HR Officer,2099-01-01,HR-REF-1\n",
     "VERIFIED_ON_IN_FUTURE"),
    ("dev-site,101,1,2026-10-01,,Enrolment sheet signed by HR,HR Officer,2026-11-01,\n", "SOURCE_REFERENCE_REQUIRED"),
    ("dev-site,101,nope,2026-10-01,,Enrolment sheet signed by HR,HR Officer,2026-11-01,HR-REF-1\n",
     "UNKNOWN_EMPLOYEE"),
    ("syd-site,110,10,2026-10-01,,Enrolment sheet signed by HR,HR Officer,2026-11-01,HR-REF-1\n", "SITE_NOT_ALLOWED"),
    ("dev-site,101,1,,,Enrolment sheet signed by HR,HR Officer,2026-11-01,HR-REF-1\n", "VALID_FROM_REQUIRED"),
])
def test_incomplete_evidence_is_an_error(api_client, db, directory, audit_calls, row, error):
    ready(api_client)
    body = _post(api_client, (HEADER + row).encode()).json()
    assert body["can_apply"] is False and body["dry_run_token"] is None
    assert error in body["rows"][0]["errors"]


def test_dry_run_never_persists(api_client, db, directory, audit_calls):
    ready(api_client)
    body = _post(api_client, (HEADER + ROW_101 + ROW_102).encode()).json()
    assert body["can_apply"] and body["dry_run_token"] and body["summary"]["rows"] == 2
    db.expire_all()
    assert db.query(IdentityMapping).count() == 0 and db.query(IdentityEvent).count() == 0


def test_apply_requires_matching_fresh_dry_run(api_client, db, directory, audit_calls, monkeypatch):
    ready(api_client)
    content = (HEADER + ROW_101).encode()
    assert _post(api_client, content, dry_run=False).json()["detail"]["error"] == "DRY_RUN_REQUIRED"
    other = _post(api_client, (HEADER + ROW_102).encode()).json()["dry_run_token"]
    assert _post(api_client, content, dry_run=False, token=other).json()["detail"]["error"] == "DRY_RUN_MISMATCH"
    stale = imp.make_token(content, 1, issued=int(time.time()) - imp.TOKEN_TTL_SECONDS - 5)
    assert _post(api_client, content, dry_run=False, token=stale).json()["detail"]["error"] == "DRY_RUN_EXPIRED"
    other_admin = imp.make_token(content, 2)
    assert _post(api_client, content, dry_run=False, token=other_admin).json()["detail"]["error"] == "DRY_RUN_MISMATCH"
    assert db.query(IdentityMapping).count() == 0


def test_apply_with_warnings_requires_acknowledgement_then_succeeds(api_client, db, directory, audit_calls):
    ready(api_client)
    content = (HEADER + ROW_101 + ROW_102).encode()
    dry = _post(api_client, content).json()
    token = dry["dry_run_token"]
    if dry["requires_warning_acknowledgement"]:
        assert _post(api_client, content, dry_run=False, token=token).status_code == 422
    resp = _post(api_client, content, dry_run=False, token=token, ack=True)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] and len(body["mappings"]) == 2
    assert {m["source"] for m in body["mappings"]} == {"IMPORT"}
    assert all("verified_by: HR Officer" in m["evidence"] for m in body["mappings"])
    assert db.query(IdentityEvent).filter_by(entity_type="IMPORT", action="IMPORT_APPLIED").count() == 1
    assert [c["action"] for c in audit_calls if c.get("entity_type") == "OnsiteIdentityImport"] == [
        "onsite.identity.import.applied"]


def test_in_file_overlap_is_an_error(api_client, db, directory, audit_calls):
    ready(api_client)
    dup = "dev-site,101,2,2026-10-05,,Enrolment sheet signed by HR,HR Officer,2026-11-01,HR-REF-009\n"
    body = _post(api_client, (HEADER + ROW_101 + dup).encode()).json()
    assert body["can_apply"] is False and "OVERLAPPING_MAPPING" in body["rows"][1]["errors"]
    assert db.query(IdentityMapping).count() == 0


def test_failed_apply_rolls_back_the_whole_batch(api_client, db, directory, audit_calls, monkeypatch):
    """Any failure after rows were inserted (here: the batch history write)
    leaves NO mapping and NO history row behind."""
    ready(api_client)
    content = (HEADER + ROW_101 + ROW_102).encode()
    token = _post(api_client, content).json()["dry_run_token"]
    from app.repositories.identity_repository import IdentityRepository

    real = IdentityRepository.add_event

    def failing(self, **kw):
        if kw.get("entity_type") == "IMPORT":
            raise RuntimeError("simulated failure at end of batch")
        return real(self, **kw)

    monkeypatch.setattr(IdentityRepository, "add_event", failing)
    with pytest.raises(RuntimeError):
        _post(api_client, content, dry_run=False, token=token, ack=True)
    db.expire_all()
    assert db.query(IdentityMapping).count() == 0
    assert db.query(IdentityEvent).count() == 0


def test_import_cannot_bypass_existing_conflicts(api_client, db, directory, audit_calls):
    ready(api_client)
    from tests.identity_helpers import create

    create(api_client, code="101", bid="1", valid_from="2026-01-01")
    body = _post(api_client, (HEADER + ROW_101).encode()).json()
    assert body["can_apply"] is False and "OVERLAPPING_MAPPING" in body["rows"][0]["errors"]
