"""Which revocation rules apply to each route of this service.

``READ``       served in every state
``OWN``        a person recording or withdrawing their own data; served in every state
``WRITE``      ordinary changes; refused only when revocation information is unavailable
``SENSITIVE``  administrative, approving, sending outside, exporting, or exposing personal
               data in bulk; served only while revocation information is current
``EXEMPT``     does not authenticate a user (health, public, service-to-service)

The method is never the deciding factor: a GET can change state. Every route must appear
here (a test enforces it); a route missing from the table is treated as SENSITIVE.
See ``auth_client_py.revocation``.
"""

from auth_client_py.revocation import EXEMPT, READ, SENSITIVE

ROUTE_POLICY: dict[str, str] = {
    # --- SENSITIVE (46)
    "GET /api/onsite/activity": SENSITIVE,
    "GET /api/onsite/activity/daily": SENSITIVE,
    "GET /api/onsite/activity/daily/export": SENSITIVE,
    "GET /api/onsite/activity/export": SENSITIVE,
    # v0.9 attendance review cases: reads expose identity-day facts; writes are
    # administrative decisions (On-site Admin only).
    "GET /api/onsite/reviews": SENSITIVE,
    "POST /api/onsite/reviews": SENSITIVE,
    "GET /api/onsite/reviews/day": SENSITIVE,
    "GET /api/onsite/reviews/{case_id}": SENSITIVE,
    "POST /api/onsite/reviews/{case_id}/reopen": SENSITIVE,
    "POST /api/onsite/reviews/{case_id}/resolve": SENSITIVE,
    "POST /api/onsite/reviews/{case_id}/submit": SENSITIVE,
    "GET /api/onsite/admin/health": SENSITIVE,
    "GET /api/onsite/admin/identity-match": SENSITIVE,
    "GET /api/onsite/admin/identity/codes/{zk_emp_code}": SENSITIVE,
    "GET /api/onsite/admin/identity/codes/{zk_emp_code}/evidence": SENSITIVE,
    "POST /api/onsite/admin/identity/codes/{zk_emp_code}/reassign": SENSITIVE,
    "GET /api/onsite/admin/identity/conflicts": SENSITIVE,
    "GET /api/onsite/admin/identity/coverage": SENSITIVE,
    "GET /api/onsite/admin/identity/directory/search": SENSITIVE,
    "POST /api/onsite/admin/identity/import": SENSITIVE,
    "GET /api/onsite/admin/identity/mappings": SENSITIVE,
    "POST /api/onsite/admin/identity/mappings": SENSITIVE,
    "GET /api/onsite/admin/identity/mappings/{mapping_id}": SENSITIVE,
    "POST /api/onsite/admin/identity/mappings/{mapping_id}/close": SENSITIVE,
    "POST /api/onsite/admin/identity/mappings/{mapping_id}/correct": SENSITIVE,
    "GET /api/onsite/admin/identity/readiness": SENSITIVE,
    "POST /api/onsite/admin/identity/rejections": SENSITIVE,
    "POST /api/onsite/admin/identity/rejections/{rejection_id}/withdraw": SENSITIVE,
    "GET /api/onsite/admin/identity/unmapped": SENSITIVE,
    "GET /api/onsite/admin/identity/unmapped/summary": SENSITIVE,
    "GET /api/onsite/admin/sites": SENSITIVE,
    "GET /api/onsite/admin/sites/{site_id}": SENSITIVE,
    "PUT /api/onsite/admin/sites/{site_id}": SENSITIVE,
    "GET /api/onsite/dashboard/overview/export": SENSITIVE,
    "GET /api/onsite/dashboard/recent-activity": SENSITIVE,
    "GET /api/onsite/employees": SENSITIVE,
    "GET /api/onsite/employees/by-id/{bamboohr_id}": SENSITIVE,
    "GET /api/onsite/employees/by-id/{bamboohr_id}/photo": SENSITIVE,
    "GET /api/onsite/employees/export": SENSITIVE,
    "GET /api/onsite/employees/{emp_code}": SENSITIVE,
    "GET /api/onsite/employees/{emp_code}/photo": SENSITIVE,
    "GET /api/onsite/exceptions": SENSITIVE,
    "GET /api/onsite/exceptions/export": SENSITIVE,
    "POST /api/onsite/sync": SENSITIVE,
    "GET /api/onsite/today": SENSITIVE,
    "GET /api/onsite/today/export": SENSITIVE,
    # --- READ (9)
    "GET /api/onsite/dashboard/activity-trend": READ,
    "GET /api/onsite/dashboard/hourly-activity": READ,
    "GET /api/onsite/dashboard/overview": READ,
    "GET /api/onsite/freshness": READ,
    "GET /api/onsite/me": READ,
    "GET /api/onsite/sites": READ,
    "GET /api/onsite/summary": READ,
    "GET /api/onsite/sync/history": READ,
    "GET /api/onsite/sync/runs/{run_id}": READ,
    # --- EXEMPT (4)
    "POST /api/onsite/internal/scheduled-sync": EXEMPT,
    "GET /api/onsite/metadata": EXEMPT,
    "GET /health": EXEMPT,
    "GET /health/deep": EXEMPT,
}
