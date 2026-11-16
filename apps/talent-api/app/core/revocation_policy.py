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
    # --- SENSITIVE (10)
    "PATCH /api/talent/applications/{application_id}/visibility": SENSITIVE,
    "POST /api/talent/external/grants": SENSITIVE,
    "POST /api/talent/external/grants/{public_id}/extend": SENSITIVE,
    "POST /api/talent/external/grants/{public_id}/regenerate": SENSITIVE,
    "POST /api/talent/external/grants/{public_id}/revoke": SENSITIVE,
    "POST /api/talent/integrations/recruitment/sync": SENSITIVE,
    "POST /api/talent/postings/{ref_id}/reopen-mapping": SENSITIVE,
    "POST /api/talent/postings/{ref_id}/unmap-mapping": SENSITIVE,
    "POST /api/talent/postings/{ref_id}/verify-mapping": SENSITIVE,
    "POST /api/talent/requests/{request_id}/review": SENSITIVE,
    # --- WRITE (12)
    "POST /api/talent/applications": WRITE,
    "PATCH /api/talent/applications/{application_id}/score": WRITE,
    "PATCH /api/talent/applications/{application_id}/stage": WRITE,
    "PATCH /api/talent/applications/{application_id}/status": WRITE,
    "POST /api/talent/candidates": WRITE,
    "POST /api/talent/interviews": WRITE,
    "PATCH /api/talent/interviews/{interview_id}/status": WRITE,
    "POST /api/talent/requests": WRITE,
    "POST /api/talent/requests/{request_id}/documents": WRITE,
    "POST /api/talent/requests/{request_id}/messages": WRITE,
    "POST /api/talent/requests/{request_id}/stage": WRITE,
    "POST /api/talent/requests/{request_id}/ta-status": WRITE,
    # --- READ (31)
    "GET /api/talent/applications": READ,
    "GET /api/talent/applications/paged": READ,
    "GET /api/talent/candidates": READ,
    "GET /api/talent/candidates/paged": READ,
    "GET /api/talent/candidates/{candidate_id}": READ,
    "GET /api/talent/clients": READ,
    "GET /api/talent/clients/{client_id}": READ,
    "GET /api/talent/dashboard/client": READ,
    "GET /api/talent/external/applications/{application_id}": READ,
    "GET /api/talent/external/dashboard": READ,
    "GET /api/talent/external/grants": READ,
    "GET /api/talent/external/interviews": READ,
    "GET /api/talent/external/requests": READ,
    "GET /api/talent/external/requests/{request_id}": READ,
    "GET /api/talent/external/requests/{request_id}/candidates": READ,
    "GET /api/talent/integrations/recruitment/freshness": READ,
    "GET /api/talent/integrations/recruitment/sync/history": READ,
    "GET /api/talent/integrations/recruitment/sync/latest": READ,
    "GET /api/talent/integrations/recruitment/sync/{run_id}": READ,
    "GET /api/talent/interviews": READ,
    "GET /api/talent/postings": READ,
    "GET /api/talent/postings/client-visible": READ,
    "GET /api/talent/postings/paged": READ,
    "GET /api/talent/postings/{ref_id}": READ,
    "GET /api/talent/requests": READ,
    "GET /api/talent/requests/paged": READ,
    "GET /api/talent/requests/{request_id}": READ,
    "GET /api/talent/requests/{request_id}/candidates": READ,
    "GET /api/talent/requests/{request_id}/documents": READ,
    "GET /api/talent/requests/{request_id}/messages": READ,
    "GET /api/talent/ta/dashboard": READ,
    # --- EXEMPT (5)
    "POST /api/talent/external/redeem": EXEMPT,
    "POST /api/talent/internal/recruitment/reconcile": EXEMPT,
    "GET /api/talent/summary": EXEMPT,
    "GET /health": EXEMPT,
    "GET /health/deep": EXEMPT,
}
