from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from auth_client_py.claims import InvalidTokenError, decode_claims

SECRET = "test-secret"


def _issue(**claims) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "42",
        "iat": now,
        "exp": now + timedelta(minutes=60),
        "iss": "dijione-dev-identity",
        **claims,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_decode_claims_round_trip():
    token = _issue(
        is_active=True,
        platform_role="PLATFORM_USER",
        platform_permissions=[],
        module_roles={
            "talent-flow": {
                "role": "TA_MEMBER",
                "client_id": None,
                "client_ids": [1, 2],
                "permissions": ["talent.requests.read", "talent.requests.update"],
            }
        },
    )
    claims = decode_claims(token, secret=SECRET)
    assert claims.user_id == 42
    assert claims.is_active is True
    talent = claims.module("talent-flow")
    assert talent is not None
    assert talent.role == "TA_MEMBER"
    assert talent.client_ids == [1, 2]
    assert talent.has("talent.requests.read")
    assert not talent.has("talent.requests.review")
    assert claims.module("birthday") is None


def test_decode_claims_rejects_bad_signature():
    token = jwt.encode(
        {"sub": "1", "iss": "dijione-dev-identity"}, "wrong-secret", algorithm="HS256"
    )
    with pytest.raises(InvalidTokenError):
        decode_claims(token, secret=SECRET)


def test_decode_claims_rejects_expired_token():
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "1", "iss": "dijione-dev-identity", "exp": now - timedelta(minutes=1)},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_claims(token, secret=SECRET)


def test_decode_claims_rejects_wrong_issuer():
    token = jwt.encode({"sub": "1", "iss": "someone-else"}, SECRET, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_claims(token, secret=SECRET)
