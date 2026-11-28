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

from auth_client_py.revocation import EXEMPT, OWN, READ, SENSITIVE

ROUTE_POLICY: dict[str, str] = {
    # --- SENSITIVE (15)
    "GET /api/atwork/management/audit": SENSITIVE,
    "GET /api/atwork/management/corrections": SENSITIVE,
    "GET /api/atwork/management/corrections/{request_id}": SENSITIVE,
    "POST /api/atwork/management/corrections/{request_id}/approve": SENSITIVE,
    "POST /api/atwork/management/corrections/{request_id}/reject": SENSITIVE,
    "GET /api/atwork/management/employees": SENSITIVE,
    "GET /api/atwork/management/employees/{user_id}/attendance": SENSITIVE,
    "GET /api/atwork/management/overview": SENSITIVE,
    "GET /api/atwork/management/reports/corrections": SENSITIVE,
    "GET /api/atwork/management/reports/export": SENSITIVE,
    "GET /api/atwork/management/reports/missed-checkouts": SENSITIVE,
    "GET /api/atwork/management/reports/sessions": SENSITIVE,
    "GET /api/atwork/management/reports/summary": SENSITIVE,
    "GET /api/atwork/management/sessions/{session_id}": SENSITIVE,
    "GET /api/atwork/management/settings": SENSITIVE,
    "PUT /api/atwork/management/settings": SENSITIVE,
    "GET /api/atwork/management/analytics": SENSITIVE,
    "GET /api/atwork/management/bp": SENSITIVE,
    "POST /api/atwork/management/bp": SENSITIVE,
    "POST /api/atwork/management/bp/{bp_user_id}/revoke": SENSITIVE,
    "GET /api/atwork/management/bp/{bp_user_id}/scope": SENSITIVE,
    "POST /api/atwork/management/bp/{bp_user_id}/scope": SENSITIVE,
    "DELETE /api/atwork/management/bp/{bp_user_id}/scope/{employee_user_id}": SENSITIVE,
    # --- OWN (6)
    "POST /api/atwork/attendance/breaks/end": OWN,
    "POST /api/atwork/attendance/breaks/start": OWN,
    "POST /api/atwork/attendance/check-in": OWN,
    "POST /api/atwork/attendance/check-out": OWN,
    "POST /api/atwork/corrections": OWN,
    "POST /api/atwork/corrections/{request_id}/withdraw": OWN,
    # --- READ (9)
    "GET /api/atwork/attendance/history": READ,
    "GET /api/atwork/attendance/policy": READ,
    "GET /api/atwork/attendance/sessions/{session_id}": READ,
    "GET /api/atwork/attendance/status": READ,
    "GET /api/atwork/attendance/today": READ,
    "GET /api/atwork/corrections": READ,
    "GET /api/atwork/corrections/{request_id}": READ,
    "GET /api/atwork/management/access": READ,
    "GET /api/atwork/me": READ,
    # --- EXEMPT (6)
    "POST /api/atwork/internal/notifications/retry-failed": EXEMPT,
    "POST /api/atwork/internal/notifications/run": EXEMPT,
    "GET /api/atwork/metadata": EXEMPT,
    "GET /api/atwork/summary": EXEMPT,
    "GET /health": EXEMPT,
    "GET /health/deep": EXEMPT,
}
