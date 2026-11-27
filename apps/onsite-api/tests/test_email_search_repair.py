"""v0.9.2 email search repair tests.

Covers:
  - admin_search returning None (unavailable) vs [] (no results) vs list (hits)
  - directory_search routing: admin_search first, snapshot fallback
  - email queries with '@' raise 503 when admin_search is unavailable
  - partial email without '@' falls back to snapshot when admin_search unavailable
  - mapping date correction: dry_run inventory, correction, skip gates
"""

import pytest

from tests.conftest import DIRECTORY, headers_for, internal_headers, make_mapping
from tests.identity_helpers import BASE


# ── directory_search routing ───────────────────────────────────────────────────

def _search(api_client, q, **kwargs):
    r = api_client.get(f"{BASE}/directory/search", params={"q": q}, headers=headers_for("ONSITE_ADMIN"))
    return r


def _items(r):
    """Extract the items list from a paginated directory search response."""
    body = r.json()
    if isinstance(body, list):
        return body
    return body.get("items", [])


class TestDirectorySearchRouting:
    def test_admin_search_hit_returned(self, api_client, db, monkeypatch, directory, audit_calls):
        """When admin_search returns results, they are returned (not snapshot)."""
        from app.services import workforce_directory as wf

        monkeypatch.setattr(wf, "admin_search", lambda q: [
            {"bamboohr_id": "99", "display_name": "Email Person", "employee_number": "999",
             "department": "Dev", "job_title": "Dev", "employment_status": "Active",
             "hire_date": "2026-01-01"},
        ])
        r = _search(api_client, "person@example.com")
        assert r.status_code == 200
        assert any(e["bamboohr_id"] == "99" for e in _items(r))

    def test_admin_search_unavailable_email_returns_503(self, api_client, db, monkeypatch, directory, audit_calls):
        """When admin_search returns None and query has '@', return 503."""
        from app.services import workforce_directory as wf

        monkeypatch.setattr(wf, "admin_search", lambda q: None)
        r = _search(api_client, "person@example.com")
        assert r.status_code == 503

    def test_admin_search_unavailable_name_uses_snapshot(self, api_client, db, monkeypatch, directory, audit_calls):
        """When admin_search returns None and query is a plain name, snapshot is used."""
        from app.services import workforce_directory as wf

        monkeypatch.setattr(wf, "admin_search", lambda q: None)
        r = _search(api_client, "101")  # matches employee_number "101" in DIRECTORY
        assert r.status_code == 200
        # Employee "1" (employee_number "101") should be found via snapshot
        assert any(e["bamboohr_id"] == "1" for e in _items(r))

    def test_admin_search_empty_means_no_results(self, api_client, db, monkeypatch, directory, audit_calls):
        """When admin_search returns [] (live but no match), empty list is returned."""
        from app.services import workforce_directory as wf

        monkeypatch.setattr(wf, "admin_search", lambda q: [])
        r = _search(api_client, "xyznonexistent@example.com")
        assert r.status_code == 200
        assert _items(r) == []

    def test_at_domain_search_uses_admin_path(self, api_client, db, monkeypatch, directory, audit_calls):
        """@domain queries go through admin_search."""
        from app.services import workforce_directory as wf

        called_with = []
        monkeypatch.setattr(wf, "admin_search", lambda q: called_with.append(q) or [])
        _search(api_client, "@dijitalteam.com")
        assert called_with, "admin_search should have been called"
        assert "@dijitalteam.com" in called_with[0]

    def test_partial_email_without_at_uses_admin_path(self, api_client, db, monkeypatch, directory, audit_calls):
        """Partial email (e.g. ahmed.thaha) also goes through admin_search."""
        from app.services import workforce_directory as wf

        admin_hits = [{"bamboohr_id": "77", "display_name": "Thaha Munowwar", "employee_number": "426",
                       "department": "IT", "job_title": "Dev", "employment_status": "Active",
                       "hire_date": "2026-05-04"}]
        monkeypatch.setattr(wf, "admin_search", lambda q: admin_hits)
        r = _search(api_client, "ahmed.thaha")
        assert r.status_code == 200
        assert any(e["display_name"] == "Thaha Munowwar" for e in _items(r))


# ── mapping date correction service ───────────────────────────────────────────

class TestMappingDateCorrection:
    def _directory_with_hire_dates(self, monkeypatch):
        """Patch the workforce directory load to return employees with hire dates."""
        import app.services.mapping_date_correction as corr
        from app.services.workforce_directory import DirectorySnapshot

        entries = [
            {"bamboohr_id": "1", "employee_number": "101", "display_name": "A",
             "employment_status": "Active", "hire_date": "2020-01-01"},
            {"bamboohr_id": "2", "employee_number": "102", "display_name": "B",
             "employment_status": "Active", "hire_date": "2026-03-01"},
        ]
        snap = DirectorySnapshot(available=True, entries=entries)
        monkeypatch.setattr(corr, "_load_directory", lambda: snap)

    def test_dry_run_does_not_commit(self, db, monkeypatch, directory, audit_calls):
        """dry_run=True should report corrections without committing."""
        from app.services import mapping_date_correction as corr

        self._directory_with_hire_dates(monkeypatch)
        m = make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-10-01")
        report = corr.run(db, dry_run=True)
        assert report.dry_run is True
        assert report.corrected == 1
        # Mapping still at original date (not committed)
        db.expire_all()
        from sqlalchemy import select
        from app.models.identity import IdentityMapping, MAPPING_VERIFIED
        still_there = db.execute(select(IdentityMapping).where(
            IdentityMapping.id == m.id,
            IdentityMapping.status == MAPPING_VERIFIED,
        )).scalars().first()
        assert still_there is not None
        assert still_there.valid_from.isoformat() == "2026-10-01"

    def test_correction_applied_when_dry_run_false(self, db, monkeypatch, directory, audit_calls):
        """dry_run=False should supersede old mapping and create replacement."""
        from app.services import mapping_date_correction as corr

        self._directory_with_hire_dates(monkeypatch)
        m = make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-10-01")
        report = corr.run(db, dry_run=False)
        assert report.corrected == 1
        db.expire_all()
        from sqlalchemy import select
        from app.models.identity import IdentityMapping, MAPPING_SUPERSEDED, MAPPING_VERIFIED
        old = db.execute(select(IdentityMapping).where(IdentityMapping.id == m.id)).scalars().first()
        assert old.status == MAPPING_SUPERSEDED
        new = db.execute(select(IdentityMapping).where(
            IdentityMapping.bamboohr_id == "1",
            IdentityMapping.status == MAPPING_VERIFIED,
        )).scalars().first()
        assert new is not None
        assert new.valid_from.isoformat() == "2020-01-01"

    def test_already_aligned_skipped(self, db, monkeypatch, directory, audit_calls):
        """Mapping with valid_from == hire_date should be skipped as already_aligned."""
        from app.services import mapping_date_correction as corr

        self._directory_with_hire_dates(monkeypatch)
        make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
        report = corr.run(db, dry_run=True)
        assert report.already_aligned == 1
        assert report.corrected == 0

    def test_hire_date_missing_skipped(self, db, monkeypatch, directory, audit_calls):
        """Mapping for employee with no hire_date should be skipped."""
        import app.services.mapping_date_correction as corr
        from app.services.workforce_directory import DirectorySnapshot

        entries = [{"bamboohr_id": "1", "employee_number": "101", "display_name": "A",
                    "employment_status": "Active", "hire_date": None}]
        snap = DirectorySnapshot(available=True, entries=entries)
        monkeypatch.setattr(corr, "_load_directory", lambda: snap)
        make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-10-01")
        report = corr.run(db, dry_run=True)
        assert report.hire_date_missing == 1

    def test_hire_date_after_current_skipped(self, db, monkeypatch, directory, audit_calls):
        """When hire_date > valid_from, skip (unusual, needs manual review)."""
        from app.services import mapping_date_correction as corr

        self._directory_with_hire_dates(monkeypatch)
        # bamboohr_id "2" has hire_date 2026-03-01, mapping valid_from 2026-01-01 (earlier)
        make_mapping(db, code="102", bamboohr_id="2", valid_from="2026-01-01")
        report = corr.run(db, dry_run=True)
        assert report.hire_date_after_current == 1

    def test_overlap_conflict_skipped(self, db, monkeypatch, directory, audit_calls):
        """Skip when moving valid_from earlier would overlap an existing mapping."""
        import app.services.mapping_date_correction as corr
        from app.services.workforce_directory import DirectorySnapshot

        entries = [
            {"bamboohr_id": "9", "employee_number": "109", "display_name": "X",
             "employment_status": "Active", "hire_date": "2026-01-01"},
            {"bamboohr_id": "10", "employee_number": "110", "display_name": "Y",
             "employment_status": "Active", "hire_date": "2026-01-01"},
        ]
        snap = DirectorySnapshot(available=True, entries=entries)
        monkeypatch.setattr(corr, "_load_directory", lambda: snap)
        # Previous owner of same code ending 2026-05-31
        make_mapping(db, code="200", bamboohr_id="9", valid_from="2026-01-01", valid_to="2026-05-31")
        # Current owner starting 2026-06-01, hire date 2026-01-01 (earlier than 2026-06-01, overlaps!)
        make_mapping(db, code="200", bamboohr_id="10", valid_from="2026-06-01")
        report = corr.run(db, dry_run=True)
        bhrid10_row = next((r for r in report.rows if r.bamboohr_id == "10"), None)
        assert bhrid10_row is not None
        assert bhrid10_row.action == "SKIPPED"

    def test_idempotent_second_run(self, db, monkeypatch, directory, audit_calls):
        """Running correction twice should not apply the same fix again."""
        from app.services import mapping_date_correction as corr

        self._directory_with_hire_dates(monkeypatch)
        make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-10-01")
        report1 = corr.run(db, dry_run=False)
        assert report1.corrected == 1
        report2 = corr.run(db, dry_run=False)
        # Second run: the replacement is now already aligned
        assert report2.corrected == 0
        assert report2.already_aligned == 1


# ── correction management endpoint ────────────────────────────────────────────

class TestCorrectionEndpoint:
    def test_dry_run_default(self, api_client, db, monkeypatch, directory, audit_calls):
        """POST /api/onsite/internal/admin/correct-mapping-dates defaults to dry_run."""
        import app.services.mapping_date_correction as corr
        from app.services.workforce_directory import DirectorySnapshot

        entries = [{"bamboohr_id": "1", "employee_number": "101", "display_name": "A",
                    "employment_status": "Active", "hire_date": "2020-01-01"}]
        snap = DirectorySnapshot(available=True, entries=entries)
        monkeypatch.setattr(corr, "_load_directory", lambda: snap)
        make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-10-01")
        r = api_client.post(
            "/api/onsite/internal/ops/correct-mapping-dates",
            headers=internal_headers(),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        assert body["corrected"] == 1  # would have been corrected

    def test_requires_internal_token(self, api_client, db, directory, audit_calls):
        """Endpoint must reject calls without the internal service token."""
        r = api_client.post("/api/onsite/internal/ops/correct-mapping-dates",
                            headers=headers_for("ONSITE_ADMIN"))
        assert r.status_code in (401, 403)
