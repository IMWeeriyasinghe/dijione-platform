"""Which revocation rules apply to each route of this service. See
``auth_client_py.revocation`` for the classes; every route must appear here (a test
enforces it) and an unlisted route is treated as SENSITIVE."""

from auth_client_py.revocation import EXEMPT, READ

ROUTE_POLICY: dict[str, str] = {
    # --- READ (2)
    "GET /api/spark/summary": READ,
    "GET /api/spark/whoami": READ,
    # --- EXEMPT (3)
    "GET /api/spark/metadata": EXEMPT,
    "GET /health": EXEMPT,
    "GET /health/deep": EXEMPT,
}
