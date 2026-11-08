from auth_client_py.fastapi_deps import make_get_claims

from app.core.config import get_settings

_settings = get_settings()

# Claims are verified locally (no call to platform-api), like every module.
get_claims = make_get_claims(secret=_settings.platform_jwt_secret, algorithm=_settings.jwt_algorithm)
