import httpx
import pytest

from auth_client_py import WorkforceDirectoryClient


def _client(handler) -> WorkforceDirectoryClient:
    transport = httpx.MockTransport(handler)
    return WorkforceDirectoryClient(
        base_url="http://people-api",
        internal_secret="s3cr3t",
        caller="consumer-api",
        client=httpx.Client(transport=transport, base_url="http://people-api"),
    )


def test_list_entries_sends_internal_headers_and_status_filter():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["status"] = request.url.params.get("status")
        seen["token"] = request.headers.get("x-internal-token")
        seen["caller"] = request.headers.get("x-internal-caller")
        return httpx.Response(200, json=[{"bamboohr_id": "1", "employee_number": "0107"}])

    rows = _client(handler).list_entries()
    assert rows == [{"bamboohr_id": "1", "employee_number": "0107"}]
    assert seen == {
        "path": "/api/people/workforce-directory", "status": "all",
        "token": "s3cr3t", "caller": "consumer-api",
    }


def test_request_sync_posts_caller_identity():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(202, json={"run_id": "r1", "status": "QUEUED", "started": True, "message": "Sync started"})

    out = _client(handler).request_sync(requested_by_application="consumer", requested_by_user_id=7)
    assert out["run_id"] == "r1"
    assert seen["path"] == "/api/people/internal/workforce-directory/sync"
    assert b'"requested_by_application":"consumer"' in seen["body"].replace(b" ", b"")


def test_errors_raise():
    with pytest.raises(httpx.HTTPStatusError):
        _client(lambda r: httpx.Response(503)).get_freshness()
