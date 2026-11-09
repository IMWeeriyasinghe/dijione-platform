"""The real Lever client against a simulated Lever: paging, retries, timeouts."""

import httpx
import pytest

from app.integrations.lever import live_client as module
from app.integrations.lever.live_client import LeverApiError, LiveLeverClient

REAL_CLIENT = httpx.Client


@pytest.fixture()
def lever(monkeypatch):
    calls = []

    def install(handler):
        def wrapped(request):
            calls.append(request)
            return handler(request, len(calls))

        monkeypatch.setattr(
            module.httpx, "Client",
            lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(wrapped), **kw),
        )
        monkeypatch.setattr(module.time, "sleep", lambda s: None)
        return LiveLeverClient()

    install.calls = calls
    return install


def test_every_page_is_read_and_only_gets_are_sent(lever):
    def pages(request, n):
        if n < 3:
            return httpx.Response(200, json={"data": [{"n": n}], "hasNext": True, "next": f"c{n}"})
        return httpx.Response(200, json={"data": [{"n": n}], "hasNext": False})

    rows = lever(pages)._paginate("/opportunities")
    assert [r["n"] for r in rows] == [1, 2, 3]
    assert lever.calls[1].url.params["offset"] == "c1"
    assert {r.method for r in lever.calls} == {"GET"}


@pytest.mark.parametrize("status", [429, 503])
def test_a_temporary_status_is_retried_then_succeeds(lever, status):
    def flaky(request, n):
        return httpx.Response(status) if n == 1 else httpx.Response(200, json={"data": [], "hasNext": False})

    assert lever(flaky)._paginate("/postings") == []
    assert len(lever.calls) == 2


def test_rate_limiting_that_never_clears_fails_the_read(lever):
    with pytest.raises(LeverApiError):
        lever(lambda r, n: httpx.Response(429))._paginate("/postings")
    assert len(lever.calls) == module._MAX_RETRIES


def test_a_failure_on_a_later_page_does_not_return_partial_rows(lever):
    def later(request, n):
        if n == 1:
            return httpx.Response(200, json={"data": [{}], "hasNext": True, "next": "c"})
        return httpx.Response(500)

    with pytest.raises(LeverApiError):
        lever(later)._paginate("/opportunities")


def test_timeouts_are_retried_and_then_fail(lever):
    def slow(request, n):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LeverApiError):
        lever(slow)._paginate("/postings")
    assert len(lever.calls) == module._MAX_RETRIES


def test_a_client_error_is_not_retried(lever):
    with pytest.raises(LeverApiError):
        lever(lambda r, n: httpx.Response(403))._paginate("/postings")
    assert len(lever.calls) == 1
