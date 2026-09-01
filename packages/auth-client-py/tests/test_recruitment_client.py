import httpx
import pytest

from auth_client_py import RecruitmentSourceClient


def _client(handler) -> RecruitmentSourceClient:
    transport = httpx.MockTransport(handler)
    return RecruitmentSourceClient(
        base_url="http://recruitment-api",
        internal_secret="s3cr3t",
        caller="talent-api",
        client=httpx.Client(transport=transport, base_url="http://recruitment-api"),
    )


def test_list_postings_sends_internal_headers_and_returns_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("x-internal-token")
        seen["caller"] = request.headers.get("x-internal-caller")
        return httpx.Response(200, json=[{"external_id": "p1", "title": "Role"}])

    rows = _client(handler).list_postings()
    assert rows == [{"external_id": "p1", "title": "Role"}]
    assert seen == {"token": "s3cr3t", "caller": "talent-api"}


def test_get_posting_404_returns_none():
    client = _client(lambda req: httpx.Response(404, json={"detail": "nope"}))
    assert client.get_posting("missing") is None


def test_read_failure_raises():
    client = _client(lambda req: httpx.Response(503, text="down"))
    with pytest.raises(httpx.HTTPError):
        client.list_postings()


def test_request_sync_posts_and_returns_202_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(202, json={"run_id": "r1", "status": "QUEUED", "started": True, "message": "ok"})

    body = _client(handler).request_sync(requested_by_user_id=5)
    assert body["run_id"] == "r1" and body["started"] is True
