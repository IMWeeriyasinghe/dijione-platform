from auth_client_py.fastapi_deps import make_get_claims, make_verify_internal_request

from app.core.config import get_settings

_settings = get_settings()

# Available for the first real spark internal endpoint (there is none yet) —
# every backend service exposes the same shared s2s gate.
require_internal_service = make_verify_internal_request(
    secret=_settings.internal_service_secret
)

# Platform Core authorization integration seam (CR §10): spark-api
# authorizes exactly the way talent-api does — decoding Platform Core's
# signed JWT claims locally, no database, no synchronous call back. There is
# no "spark" module role for anyone to hold yet (COMING_SOON, CR §36), so
# nothing uses this to gate a real capability today; it exists so the next
# phase can add ``claims.module("spark")`` checks without touching the
# authorization plumbing.
get_claims = make_get_claims(secret=_settings.jwt_dev_secret, algorithm=_settings.jwt_algorithm)
