"""Stage 1: verified identity resolution (interval semantics, no numeric matching)."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.constants import MappingStatus
from app.services.identity_resolution import MappingIndex, MappingPeriod, legacy_identity_class
from app.services.workforce_directory import DirectorySnapshot
from tests.conftest import DIRECTORY, make_mapping

D = date.fromisoformat
DIR = DirectorySnapshot(available=True, entries=DIRECTORY)


def _idx(*periods, directory=DIR):
    return MappingIndex([MappingPeriod(i + 1, *p) for i, p in enumerate(periods)], directory)


def test_numeric_equality_never_attributes():
    # Directory has employee_number "101" (bamboohr 1) but no mapping exists.
    r = _idx().resolve("dev-site", "101", D("2026-10-13"))
    assert r.mapping_status == MappingStatus.UNMAPPED and r.bamboohr_id is None and r.employee_name is None


def test_inclusive_boundaries_and_reassignment_d_minus_1_d():
    idx = _idx(("s", "131", "1", D("2025-01-10"), D("2025-05-31")), ("s", "131", "2", D("2025-06-01"), None))
    assert idx.resolve("s", "131", D("2025-01-09")).mapping_status == MappingStatus.UNMAPPED  # before ownership
    assert idx.resolve("s", "131", D("2025-01-10")).bamboohr_id == "1"
    assert idx.resolve("s", "131", D("2025-05-31")).bamboohr_id == "1"
    assert idx.resolve("s", "131", D("2025-06-01")).bamboohr_id == "2"
    assert idx.resolve("s", "131", D("2030-01-01")).bamboohr_id == "2"


def test_gap_day_stays_unmapped():
    idx = _idx(("s", "9", "1", D("2025-01-01"), D("2025-01-10")), ("s", "9", "2", D("2025-01-12"), None))
    assert idx.resolve("s", "9", D("2025-01-11")).mapping_status == MappingStatus.UNMAPPED


def test_site_scoped():
    idx = _idx(("a", "9", "1", D("2025-01-01"), None))
    assert idx.resolve("b", "9", D("2025-02-01")).mapping_status == MappingStatus.UNMAPPED


def test_overlap_is_defensive_conflict_never_attributed():
    idx = _idx(("s", "9", "1", D("2025-01-01"), None), ("s", "9", "2", D("2025-03-01"), None))
    r = idx.resolve("s", "9", D("2025-03-05"))
    assert r.mapping_status == MappingStatus.MAPPING_CONFLICT and r.bamboohr_id is None and not r.identified


def test_directory_missing_and_unavailable_keep_attribution_without_live_name():
    idx = _idx(("s", "9", "999999", D("2025-01-01"), None, "77", "Snapshot Name"))
    r = idx.resolve("s", "9", D("2025-02-01"))
    assert r.mapping_status == MappingStatus.MAPPED_DIRECTORY_MISSING and r.identified
    assert r.employee_name == "Snapshot Name" and r.has_photo is False
    down = _idx(("s", "9", "1", D("2025-01-01"), None), directory=DirectorySnapshot(available=False))
    r = down.resolve("s", "9", D("2025-02-01"))
    assert r.mapping_status == MappingStatus.DIRECTORY_UNAVAILABLE and r.identified and r.bamboohr_id == "1"
    assert legacy_identity_class(r, D("2025-02-01"), D("2025-02-01")) is None


def test_multiple_codes_one_employee_and_windows():
    idx = _idx(("s", "10", "1", D("2025-01-01"), D("2025-03-31")), ("s", "11", "1", D("2025-04-01"), None))
    assert idx.resolve("s", "10", D("2025-02-01")).bamboohr_id == idx.resolve("s", "11", D("2025-05-01")).bamboohr_id
    assert sorted(idx.windows("s", D("2025-03-01"), D("2025-04-30"))) == [
        ("10", D("2025-03-01"), D("2025-03-31")), ("11", D("2025-04-01"), D("2025-04-30"))]
    assert set(idx.employees_in_period("s", D("2025-03-01"), D("2025-04-30"))) == {"1"}


def test_legacy_class_derived_from_mapped_employee():
    idx = _idx(("s", "a", "3", D("2020-01-01"), None), ("s", "b", "8", D("2020-01-01"), None))
    inactive = idx.resolve("s", "a", D("2026-10-14"))  # bamboohr 3 terminated 2025-08-31
    assert legacy_identity_class(inactive, D("2026-10-14"), D("2026-10-14")) == "MATCHED_INACTIVE"
    before = idx.resolve("s", "b", D("2026-10-14"))  # bamboohr 8 hired 2026-12-01
    assert legacy_identity_class(before, D("2026-10-14"), D("2026-10-14")) == "MATCHED_BEFORE_HIRE"


def test_index_loads_only_verified_rows_for_allowed_sites(db):
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    make_mapping(db, site_id="hidden-site", code="101", bamboohr_id="2", valid_from="2020-01-01")
    s = make_mapping(db, code="102", bamboohr_id="2", valid_from="2020-01-01", valid_to="2020-12-31")
    s.status = "SUPERSEDED"
    db.commit()
    idx = MappingIndex.load(db, allowed_site_ids=("dev-site",), directory=DIR)
    assert idx.resolve("dev-site", "101", D("2026-01-01")).bamboohr_id == "1"
    assert idx.resolve("dev-site", "102", D("2020-06-01")).mapping_status == MappingStatus.UNMAPPED
    assert idx.resolve("hidden-site", "101", D("2026-01-01")).mapping_status == MappingStatus.UNMAPPED


def test_open_ended_partial_unique_index(db):
    make_mapping(db, code="9", bamboohr_id="1", valid_from="2025-01-01")
    with pytest.raises(IntegrityError):
        make_mapping(db, code="9", bamboohr_id="2", valid_from="2026-01-01")
    db.rollback()
    # A closed period alongside an open one is allowed by the index (the
    # service enforces non-overlap).
    make_mapping(db, code="9", bamboohr_id="2", valid_from="2024-01-01", valid_to="2024-12-31")


def test_period_check_constraint(db):
    with pytest.raises(IntegrityError):
        make_mapping(db, code="9", bamboohr_id="1", valid_from="2025-02-01", valid_to="2025-01-01")
    db.rollback()
