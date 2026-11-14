"""Shared helpers for the Identity Management tests (synthetic data only)."""

from tests.conftest import enable_site, headers_for, run_sync

BASE = "/api/onsite/admin/identity"
EVIDENCE = "IT enrolment sheet row 12, confirmed by HR (synthetic)"


def ready(api_client, *sites):
    run_sync(api_client)
    for s in sites or ("dev-site",):
        enable_site(api_client, s)


def create(api_client, *, code, bid, valid_from, valid_to=None, site="dev-site", ack=True, evidence=EVIDENCE,
           role="ONSITE_ADMIN"):
    body = {"site_id": site, "zk_emp_code": code, "bamboohr_id": bid, "valid_from": valid_from,
            "valid_to": valid_to, "evidence": evidence}
    resp = api_client.post(f"{BASE}/mappings", json=body, headers=headers_for(role))
    if ack and resp.status_code == 422 and resp.json()["detail"].get("error") == "WARNINGS_NOT_ACKNOWLEDGED":
        body["acknowledged_warnings"] = resp.json()["detail"]["unacknowledged"]
        resp = api_client.post(f"{BASE}/mappings", json=body, headers=headers_for(role))
    return resp
