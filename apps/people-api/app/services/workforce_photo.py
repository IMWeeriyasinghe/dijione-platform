"""Fetch a BambooHR profile photo from its stored ``photo_url``.

Same safeguards Customer Portal V2 uses for the same BambooHR links: https
only (including every redirect hop — SSRF defence), the real image type is
sniffed because BambooHR's CDN serves ``application/octet-stream``, and any
failure is "no photo" rather than an error. Adds a size cap and reports
throttling (429) separately so callers can back off instead of caching a
miss for a long time.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

MAX_BYTES = 2_000_000
_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@dataclass
class PhotoResult:
    content: bytes | None = None
    content_type: str | None = None
    throttled: bool = False
    retry_after: int = 60


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def fetch(url: str, *, client: httpx.Client | None = None) -> PhotoResult:
    if not url.lower().startswith("https://"):
        return PhotoResult()
    try:
        get = client.get if client is not None else httpx.get
        resp = get(url, timeout=10.0, follow_redirects=True)
    except httpx.HTTPError:
        return PhotoResult()
    if any(not str(r.url).lower().startswith("https://") for r in getattr(resp, "history", ())) or \
            not str(resp.url).lower().startswith("https://"):
        return PhotoResult()
    if resp.status_code == 429:
        try:
            retry = int(resp.headers.get("Retry-After", "60"))
        except ValueError:
            retry = 60
        return PhotoResult(throttled=True, retry_after=max(1, min(retry, 3600)))
    if resp.status_code != 200 or not resp.content or len(resp.content) > MAX_BYTES:
        return PhotoResult()
    header = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    content_type = sniff(resp.content) or (header if header in _TYPES else None)
    if content_type is None:
        return PhotoResult()
    return PhotoResult(content=resp.content, content_type=content_type)
