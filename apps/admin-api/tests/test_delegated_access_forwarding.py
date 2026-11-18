"""admin-api forwards the Central Admin delegated-access endpoints unchanged (method, path, body,
break-glass query) with the caller's own token; Platform Core decides who may."""

import json

import pytest

HEADERS = {"Authorization": "Bearer valid-admin-token"}  # the token the stub Platform Core accepts
P = "/api/platform/admin"


@pytest.mark.parametrize(
    ("method", "path", "body", "expected_path"),
    [
        ("get", "/api/admin/applications/talent-flow/administrators", None,
         f"{P}/applications/talent-flow/administrators"),
        ("put", "/api/admin/applications/talent-flow/administrators/7", {"grantable_roles": ["TA_MEMBER"]},
         f"{P}/applications/talent-flow/administrators/7"),
        ("get", "/api/admin/applications/talent-flow/suspensions", None, f"{P}/applications/talent-flow/suspensions"),
        ("patch", "/api/admin/modules/talent-flow", {"enabled": False}, f"{P}/modules/talent-flow"),
    ],
)
def test_forwarded_unchanged(api_client, method, path, body, expected_path):
    kwargs = {"headers": HEADERS, **({"json": body} if body is not None else {})}
    resp = getattr(api_client, method)(path, **kwargs)
    assert resp.status_code == 200, resp.text
    echo = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
    assert echo["method"] == method.upper() and echo["path"] == expected_path
    if body is not None:
        assert json.loads(echo["body"]) == body


@pytest.mark.parametrize("kind", ["administrators", "suspensions"])
def test_deletes_carry_the_break_glass_reason(api_client, kind):
    resp = api_client.delete(f"/api/admin/applications/talent-flow/{kind}/7?break_glass_reason=Covering%20today",
                             headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["query"] == {"break_glass_reason": "Covering today"}
    plain = api_client.delete(f"/api/admin/applications/talent-flow/{kind}/7", headers=HEADERS)
    assert plain.json()["query"] == {}


def test_missing_token_is_refused_locally(api_client):
    assert api_client.put("/api/admin/applications/talent-flow/administrators/7", json={}).status_code == 401
