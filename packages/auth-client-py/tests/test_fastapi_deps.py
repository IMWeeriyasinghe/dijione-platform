from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from auth_client_py.fastapi_deps import make_verify_internal_request

_SECRET = "shared-internal-secret"

app = FastAPI()
require_internal = make_verify_internal_request(secret=_SECRET)


@app.get("/internal/ping")
def ping(caller: str | None = Depends(require_internal)) -> dict:
    return {"caller": caller}


client = TestClient(app)


def test_missing_token_is_rejected():
    assert client.get("/internal/ping").status_code == 401


def test_wrong_token_is_rejected():
    resp = client.get("/internal/ping", headers={"X-Internal-Token": "nope"})
    assert resp.status_code == 401


def test_correct_token_passes_and_returns_caller():
    resp = client.get(
        "/internal/ping",
        headers={"X-Internal-Token": _SECRET, "X-Internal-Caller": "talent-api"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"caller": "talent-api"}


def test_correct_token_without_caller_header_is_still_allowed():
    resp = client.get("/internal/ping", headers={"X-Internal-Token": _SECRET})
    assert resp.status_code == 200
    assert resp.json() == {"caller": None}
