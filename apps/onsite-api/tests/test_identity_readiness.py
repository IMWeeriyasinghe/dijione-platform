"""Stage 2: readiness report — figures only, distinct identities, never pass/fail."""

from datetime import date

from app.services import identity_admin_service as ia
from tests.conftest import make_mapping
from tests.identity_helpers import ready


def test_readiness_figures(api_client, db, directory, audit_calls):
    ready(api_client)
    # 101 and 0107 both belong to bamboohr 1 -> ONE identified employee.
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-01-01")
    make_mapping(db, code="0107", bamboohr_id="1", valid_from="2026-01-01")
    actor = ia.Actor(user_id=1, allowed_site_ids=("dev-site",))
    r = ia.readiness(db, actor, directory, site_id="dev-site", days=30, today=date(2026, 10, 14))
    # dev-site 13-14 Oct: 101 x3, 102 x1, 0107 x2, 999 x1, 103 x1, 105 x1, TEST-AZURE-001 x1 = 10
    assert (r["total_punches"], r["identified_punches"], r["identified_employees"]) == (10, 5, 1)
    assert r["active_codes"] == 7 and r["unmapped_codes"] == 5 and r["unmapped_punches"] == 5
    assert r["identified_punch_pct"] == 50.0 and r["mappings_without_evidence"] == 0
    assert {c["zk_emp_code"] for c in r["high_volume_outstanding_codes"]} == {"102", "999", "103", "105",
                                                                             "TEST-AZURE-001"}
    assert r["decision"].startswith("NOT_AUTOMATIC") and "pass" not in r
