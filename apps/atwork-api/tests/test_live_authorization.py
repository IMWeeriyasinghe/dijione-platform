"""Management routes re-check Platform Core, so older tokens cannot outlive a revocation."""

import pytest

from app.api import deps
from tests.test_corrections_management import MANAGER, MGMT, M, hdr

URL = f"{M}/overview"
LIVE = frozenset(MANAGER)


@pytest.fixture(autouse=True)
def live(monkeypatch):
    deps._live_cache.clear()
    monkeypatch.setattr(deps, "_live_check_enabled", lambda: True)
    yield
    deps._live_cache.clear()


def serve(monkeypatch, answer):
    calls = []

    def fetch(user_id):
        calls.append(user_id)
        return answer

    monkeypatch.setattr(deps, "_fetch_live_permissions", fetch)
    return calls


def test_current_manager_is_allowed(api_client, monkeypatch):
    serve(monkeypatch, LIVE)
    assert api_client.get(URL, headers=hdr(50, MANAGER)).status_code == 200


def test_revoked_manager_with_an_older_token_is_refused(api_client, monkeypatch):
    serve(monkeypatch, frozenset(MANAGER[:4]))
    assert api_client.get(URL, headers=hdr(50, MANAGER)).status_code == 403


def test_deactivated_user_is_refused(api_client, monkeypatch):
    serve(monkeypatch, frozenset())
    assert api_client.get(URL, headers=hdr(50, MANAGER)).status_code == 403


def test_unconfirmed_answer_fails_closed_and_is_not_cached(api_client, monkeypatch):
    calls = serve(monkeypatch, None)
    assert [api_client.get(URL, headers=hdr(50, MANAGER)).status_code for _ in range(2)] == [503, 503]
    assert len(calls) == 2


def test_answers_are_cached_briefly(api_client, monkeypatch):
    calls = serve(monkeypatch, LIVE)
    for _ in range(3):
        api_client.get(URL, headers=hdr(50, MANAGER))
    assert calls == [50]


def test_employee_token_never_reaches_the_live_check(api_client, monkeypatch):
    calls = serve(monkeypatch, LIVE)
    assert api_client.get(URL, headers=hdr(50, MANAGER[:4])).status_code == 403
    assert calls == []


def test_employee_routes_do_not_depend_on_platform_core(api_client, monkeypatch):
    serve(monkeypatch, None)
    assert api_client.get("/api/atwork/attendance/status", headers=hdr(50, MANAGER[:4])).status_code == 200
    assert MGMT in MANAGER
