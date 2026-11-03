"""Workforce Directory profile photos: BambooHR photoUrl (directory endpoint),
stored server-side and served only through the internal-token proxy."""

import httpx

from app.integrations.bamboohr.workforce_mapper import map_workforce_record
from app.integrations.bamboohr.workforce_schemas import BambooHRWorkforceRecord
from app.models.workforce import WorkforceDirectoryEntry
from app.services import workforce_photo
from tests.conftest import internal_headers

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _entry(db, bid="b1", url="https://images.bamboohr.example/p/1.jpg"):
    db.add(WorkforceDirectoryEntry(bamboohr_id=bid, employee_number="101", display_name="A B", photo_url=url))
    db.commit()


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_mapper_keeps_only_https_photo_links():
    base = dict(id="1", display_name="A", employment_status="Active")
    assert map_workforce_record(BambooHRWorkforceRecord(**base, photo_url="https://x/p.jpg"))["photo_url"] == "https://x/p.jpg"
    assert map_workforce_record(BambooHRWorkforceRecord(**base, photo_url="http://x/p.jpg"))["photo_url"] is None
    assert map_workforce_record(BambooHRWorkforceRecord(**base))["photo_url"] is None


def test_fetch_sniffs_type_and_rejects_non_images_and_oversize():
    octet = {"content-type": "application/octet-stream"}
    ok = workforce_photo.fetch("https://x/p", client=_client(lambda r: httpx.Response(200, content=PNG, headers=octet)))
    assert ok.content == PNG and ok.content_type == "image/png"
    html = workforce_photo.fetch("https://x/p", client=_client(lambda r: httpx.Response(200, content=b"<html>")))
    assert html.content is None
    huge = PNG + b"0" * workforce_photo.MAX_BYTES
    big = workforce_photo.fetch("https://x/p", client=_client(lambda r: httpx.Response(200, content=huge)))
    assert big.content is None
    assert workforce_photo.fetch("http://x/p").content is None


def test_fetch_reports_throttling_and_treats_errors_as_missing():
    t = workforce_photo.fetch("https://x/p", client=_client(lambda r: httpx.Response(429, headers={"Retry-After": "30"})))
    assert t.throttled and t.retry_after == 30 and t.content is None
    missing = workforce_photo.fetch("https://x/p", client=_client(lambda r: httpx.Response(404)))
    assert not missing.throttled and missing.content is None


def test_photo_route_requires_internal_token(api_client, db):
    _entry(db)
    assert api_client.get("/api/people/workforce-directory/b1/photo").status_code in (401, 403)


def test_photo_route_serves_bytes_404s_and_throttles(api_client, db, monkeypatch):
    _entry(db)
    _entry(db, bid="b2", url=None)
    monkeypatch.setattr(workforce_photo, "fetch", lambda url: workforce_photo.PhotoResult(content=PNG, content_type="image/png"))
    resp = api_client.get("/api/people/workforce-directory/b1/photo", headers=internal_headers())
    assert resp.status_code == 200 and resp.content == PNG and resp.headers["content-type"] == "image/png"
    assert resp.headers["cache-control"] == "private, max-age=86400"
    assert api_client.get("/api/people/workforce-directory/b2/photo", headers=internal_headers()).status_code == 404
    assert api_client.get("/api/people/workforce-directory/nope/photo", headers=internal_headers()).status_code == 404
    monkeypatch.setattr(workforce_photo, "fetch", lambda url: workforce_photo.PhotoResult(throttled=True, retry_after=12))
    t = api_client.get("/api/people/workforce-directory/b1/photo", headers=internal_headers())
    assert t.status_code == 503 and t.headers["retry-after"] == "12"


def test_directory_lists_has_photo_flag(api_client, db):
    _entry(db)
    rows = api_client.get("/api/people/workforce-directory", headers=internal_headers()).json()
    assert rows[0]["has_photo"] is True and "photo_url" not in rows[0]
