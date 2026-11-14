"""Outstanding-ID backlog summary: review state, aging, recency, scope.

Mock data at dev-site (see test_identity_coverage): 7 IDs over 2026-10-13/14.
"""

from datetime import date

import pytest

from tests.conftest import headers_for, make_mapping
from tests.identity_helpers import BASE, ready


@pytest.fixture
def as_of(monkeypatch):
    from app.api.routes import identity_admin

    monkeypatch.setattr(identity_admin, "_site_today", lambda db, site_id: date(2026, 10, 20))


def _summary(api_client, role="ONSITE_ADMIN", site="dev-site"):
    return api_client.get(f"{BASE}/unmapped/summary?site_id={site}", headers=headers_for(role))


def test_counts_ids_by_review_state_aging_and_recency(api_client, db, directory, audit_calls, as_of):
    ready(api_client)
    s = _summary(api_client).json()
    assert s["as_of"] == "2026-10-20" and s["outstanding_ids"] == 7 and s["unmapped_punches"] == 10
    assert s["review"] == {"AWAITING_REVIEW": 7, "REJECTED_ASSOCIATION": 0, "PARTLY_VERIFIED": 0}
    aging = {b["label"]: (b["ids"], b["unmapped_punches"]) for b in s["aging"]}
    assert aging == {"0–7 days": (7, 10), "8–30 days": (0, 0), "31–90 days": (0, 0), "Over 90 days": (0, 0)}
    recency = {b["label"]: b["ids"] for b in s["recency"]}
    assert recency["Active in last 7 days"] == 7


def test_partly_verified_and_rejected_are_still_outstanding(api_client, db, directory, audit_calls, as_of):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2026-10-14")  # 13th still unmapped
    make_mapping(db, code="102", bamboohr_id="2", valid_from="2026-01-01")  # fully verified -> not outstanding
    r = api_client.post(f"{BASE}/rejections", headers=headers_for(), json={
        "site_id": "dev-site", "zk_emp_code": "103", "bamboohr_id": "3", "reason": "Different person per HR records"})
    assert r.status_code == 201, r.text
    s = _summary(api_client).json()
    assert s["outstanding_ids"] == 6
    # A rejected association is not a resolved identity: 103 stays outstanding.
    assert s["review"] == {"AWAITING_REVIEW": 4, "REJECTED_ASSOCIATION": 1, "PARTLY_VERIFIED": 1}


def test_site_scope_and_admin_only(api_client, db, directory, audit_calls, as_of):
    ready(api_client)
    assert _summary(api_client, site="syd-site").status_code == 403
    assert _summary(api_client, role="ONSITE_VIEWER").status_code == 403
    assert api_client.get(f"{BASE}/unmapped/summary?site_id=dev-site").status_code == 401
