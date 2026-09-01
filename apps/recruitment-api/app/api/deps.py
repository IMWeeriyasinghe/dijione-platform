from auth_client_py.fastapi_deps import make_verify_internal_request

from app.core.config import get_settings

_settings = get_settings()

# recruitment-api is an internal-only service: only DijiOne backends call it
# (talent-api today, DijiSpark later), always with the shared internal
# token. Browsers never reach it directly — they go through their own
# application API. The single s2s gate is defined in auth-client-py.
require_internal_service = make_verify_internal_request(secret=_settings.internal_service_secret)
