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

from auth_client_py.revocation import EXEMPT, READ, SENSITIVE, WRITE

ROUTE_POLICY: dict[str, str] = {
    # --- SENSITIVE (28)
    "POST /api/birthday/admin/run-attention": SENSITIVE,
    "POST /api/birthday/admin/run-detection": SENSITIVE,
    "GET /api/birthday/admin/scan-runs": SENSITIVE,
    "GET /api/birthday/admin/test-email-recipients": SENSITIVE,
    "POST /api/birthday/admin/test-email-recipients": SENSITIVE,
    "DELETE /api/birthday/admin/test-email-recipients/{recipient_id}": SENSITIVE,
    "PATCH /api/birthday/admin/test-email-recipients/{recipient_id}": SENSITIVE,
    "GET /api/birthday/config": SENSITIVE,
    "PATCH /api/birthday/config": SENSITIVE,
    "DELETE /api/birthday/orders/{order_id}": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/cancel": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/confirm-release": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/hold": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/release": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/reopen": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/resend": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/send-to-supplier": SENSITIVE,
    "POST /api/birthday/orders/{order_id}/verify": SENSITIVE,
    "POST /api/birthday/people/refresh": SENSITIVE,
    "POST /api/birthday/suppliers": SENSITIVE,
    "PATCH /api/birthday/suppliers/{supplier_id}": SENSITIVE,
    "POST /api/birthday/suppliers/{supplier_id}/catalogue": SENSITIVE,
    "PATCH /api/birthday/suppliers/{supplier_id}/catalogue/{item_id}": SENSITIVE,
    "POST /api/birthday/suppliers/{supplier_id}/locations": SENSITIVE,
    "POST /api/birthday/suppliers/{supplier_id}/users": SENSITIVE,
    "PATCH /api/birthday/suppliers/{supplier_id}/users/{user_id}": SENSITIVE,
    "POST /api/birthday/suppliers/{supplier_id}/users/{user_id}/impersonate": SENSITIVE,
    "POST /api/birthday/suppliers/{supplier_id}/users/{user_id}/invite": SENSITIVE,
    # --- WRITE (14)
    "POST /api/birthday/inbound-emails/{inbound_id}/dismiss": WRITE,
    "POST /api/birthday/inbound-emails/{inbound_id}/link": WRITE,
    "POST /api/birthday/orders": WRITE,
    "PATCH /api/birthday/orders/{order_id}": WRITE,
    "PATCH /api/birthday/orders/{order_id}/address-verification": WRITE,
    "PATCH /api/birthday/orders/{order_id}/delivery-address": WRITE,
    "POST /api/birthday/orders/{order_id}/issues": WRITE,
    "PATCH /api/birthday/orders/{order_id}/issues/{issue_id}/resolve": WRITE,
    "POST /api/birthday/orders/{order_id}/messages": WRITE,
    "POST /api/birthday/orders/{order_id}/special-requirements": WRITE,
    "POST /api/birthday/portal/orders/{order_id}/accept": WRITE,
    "POST /api/birthday/portal/orders/{order_id}/issues": WRITE,
    "POST /api/birthday/portal/orders/{order_id}/messages": WRITE,
    "PATCH /api/birthday/portal/orders/{order_id}/status": WRITE,
    # --- READ (23)
    "GET /api/birthday/dashboard": READ,
    "GET /api/birthday/employees/upcoming-birthdays": READ,
    "GET /api/birthday/inbound-emails": READ,
    "GET /api/birthday/orders": READ,
    "GET /api/birthday/orders/{order_id}": READ,
    "GET /api/birthday/orders/{order_id}/issues": READ,
    "GET /api/birthday/orders/{order_id}/readiness": READ,
    "GET /api/birthday/orders/{order_id}/timeline": READ,
    "GET /api/birthday/people/freshness": READ,
    "GET /api/birthday/portal/dashboard": READ,
    "GET /api/birthday/portal/me": READ,
    "GET /api/birthday/portal/orders": READ,
    "GET /api/birthday/portal/orders/{order_id}": READ,
    "GET /api/birthday/portal/orders/{order_id}/issues": READ,
    "GET /api/birthday/portal/orders/{order_id}/timeline": READ,
    "GET /api/birthday/suppliers": READ,
    "GET /api/birthday/suppliers/{supplier_id}": READ,
    "GET /api/birthday/suppliers/{supplier_id}/catalogue": READ,
    "GET /api/birthday/suppliers/{supplier_id}/locations": READ,
    "GET /api/birthday/suppliers/{supplier_id}/readiness": READ,
    "GET /api/birthday/suppliers/{supplier_id}/users": READ,
    "GET /api/birthday/upcoming": READ,
    "GET /api/birthday/whoami": READ,
    # --- EXEMPT (15)
    "POST /api/birthday/internal/dev/inbound-email": EXEMPT,
    "POST /api/birthday/internal/dev/supplier-login": EXEMPT,
    "GET /api/birthday/internal/dev/supplier-users": EXEMPT,
    "POST /api/birthday/internal/run-attention": EXEMPT,
    "POST /api/birthday/internal/run-comms": EXEMPT,
    "POST /api/birthday/internal/run-daily-scan": EXEMPT,
    "GET /api/birthday/internal/scan-runs": EXEMPT,
    "GET /api/birthday/internal/scan-runs/{run_id}": EXEMPT,
    "GET /api/birthday/metadata": EXEMPT,
    "GET /api/birthday/summary": EXEMPT,
    "GET /api/birthday/supplier/auth/config": EXEMPT,
    "GET /api/birthday/supplier/auth/login-url": EXEMPT,
    "POST /api/birthday/supplier/auth/token": EXEMPT,
    "GET /health": EXEMPT,
    "GET /health/deep": EXEMPT,
}
