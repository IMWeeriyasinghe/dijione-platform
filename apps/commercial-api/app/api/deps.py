from auth_client_py.fastapi_deps import make_verify_internal_request

from app.core.config import get_settings

_settings = get_settings()

require_internal_service = make_verify_internal_request(secret=_settings.internal_service_secret)
