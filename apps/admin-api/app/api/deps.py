from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


def get_bearer_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> str:
    """admin-api holds no identity of its own — every request must carry the
    caller's bearer token so Platform Core can authorize it itself (CR §48).
    A missing token fails fast here instead of round-tripping to Platform
    Core just to get the same 401 back."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return credentials.credentials
