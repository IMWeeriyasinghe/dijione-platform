"""Identity Management dashboard coverage: units, scoping, dates, reassignment.

Mock data at dev-site:
  2026-10-13: 101 x2, 102 x1, 0107 x2, 999 x1           (6 punches, 4 IDs)
  2026-10-14: 103 x1, 105 x1, 101 x1, TEST-AZURE-001 x1  (4 punches, 4 IDs)
"""

from tests.conftest import headers_for, make_mapping
from tests.identity_helpers import BASE, ready

RANGE = "date_from=2026-10-13&date_to=2026-10-14"


def _cov(api_client, extra="", role="ONSITE_ADMIN", site="dev-site"):
    return api_client.get(f"{BASE}/coverage?site_id={site}&{RANGE}{extra}", headers=headers_for(role))


def test_nothing_verified_counts_ids_and_punches_separately(api_client, db, directory, audit_calls):
    ready(api_client)
    c = _cov(api_client).json()
    assert c["ids"] == {"observed": 7, "verified": 0, "fully_verified": 0, "partly_verified": 0, "unmapped": 7}
    assert c["punches"] == {"total": 10, "verified": 0, "unmapped": 10, "coverage_pct": 0.0}
    assert c["verified_team_members"] == 0
    assert [t["unmapped_punches"] for t in c["trend"]] == [6, 4]
    assert c["top_unmapped"][0] == {"zk_emp_code": "101", "unmapped_punches": 3, "unmapped_days": 2,
                                    "first_unmapped": "2026-10-13", "last_unmapped": "2026-10-14", "mapped_now": False}
    assert c["ingestion"]["feed_state"] is not None


def test_two_ids_one_team_member_and_punch_coverage(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    make_mapping(db, code="0107", bamboohr_id="1", valid_from="2020-01-01")
    c = _cov(api_client).json()
    assert c["ids"]["verified"] == 2 and c["ids"]["unmapped"] == 5
    assert c["verified_team_members"] == 1  # two IDs, ONE team member — IDs are never people
    assert c["punches"] == {"total": 10, "verified": 5, "unmapped": 5, "coverage_pct": 50.0}
    assert c["trend"] == [{"date": "2026-10-13", "verified_punches": 4, "unmapped_punches": 2},
                          {"date": "2026-10-14", "verified_punches": 1, "unmapped_punches": 3}]
    assert "101" not in {x["zk_emp_code"] for x in c["top_unmapped"]}


def test_period_bound_and_reassigned_mappings_attribute_by_day(api_client, db, directory, audit_calls):
    ready(api_client)
    # 101 verified only on the 14th (A), reassigned 102: owner B until the 13th... only 13th has punches.
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-10-14")
    make_mapping(db, code="102", bamboohr_id="2", valid_from="2026-01-01", valid_to="2026-10-13")
    make_mapping(db, code="102", bamboohr_id="4", valid_from="2026-10-14")
    c = _cov(api_client).json()
    assert c["ids"]["partly_verified"] == 1  # 101: 13th unmapped, 14th verified
    assert c["ids"]["fully_verified"] == 1  # 102 (its only punch day is inside B's period)
    assert c["punches"]["verified"] == 2 and c["punches"]["unmapped"] == 8
    top = {x["zk_emp_code"]: x for x in c["top_unmapped"]}
    assert top["101"]["unmapped_punches"] == 2 and top["101"]["mapped_now"] is True
    assert c["verified_team_members"] == 2


def test_date_filter_changes_every_figure(api_client, db, directory, audit_calls):
    ready(api_client)
    c = api_client.get(f"{BASE}/coverage?site_id=dev-site&date_from=2026-10-14&date_to=2026-10-14",
                       headers=headers_for()).json()
    assert c["ids"]["observed"] == 4 and c["punches"]["total"] == 4 and len(c["trend"]) == 1
    assert api_client.get(f"{BASE}/coverage?site_id=dev-site&date_from=2026-10-15&date_to=2026-10-14",
                          headers=headers_for()).status_code == 422


def test_site_scope_and_admin_only(api_client, db, directory, audit_calls):
    ready(api_client)  # syd-site exists but is not enabled
    assert _cov(api_client, site="syd-site").status_code == 403
    assert _cov(api_client, role="ONSITE_VIEWER").status_code == 403
    assert api_client.get(f"{BASE}/coverage?site_id=dev-site").status_code == 401
