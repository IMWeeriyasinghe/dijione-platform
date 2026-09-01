from auth_client_py.claims import (
    AuthClaims,
    ExternalClaims,
    InvalidTokenError,
    ModuleRoleClaims,
    SupplierClaims,
    decode_claims,
)
from auth_client_py.people_client import EmployeeDirectoryClient
from auth_client_py.platform_client import PlatformClient
from auth_client_py.recruitment_client import RecruitmentSourceClient

# ``fastapi_deps`` (make_get_claims / make_verify_internal_request) is imported
# directly from the submodule by services — it pulls in FastAPI, which is a
# consumer dependency, not one of this package's own (see pyproject.toml).

__all__ = [
    "AuthClaims",
    "ModuleRoleClaims",
    "SupplierClaims",
    "ExternalClaims",
    "InvalidTokenError",
    "decode_claims",
    "PlatformClient",
    "RecruitmentSourceClient",
    "EmployeeDirectoryClient",
]
