"""Real, read-only production LeverClient.

Safety-by-construction: this class exposes exactly one private HTTP
helper, ``_get``, backed by ``httpx.Client.get``. No ``_post``/``_put``/
``_patch``/``_delete`` method is defined anywhere on this class, so there
is no code path here capable of issuing a write to Lever — independent of
any runtime configuration or check. CLAUDE.md §60 LIVE LEVER SAFETY
CONTRACT applies unconditionally: GET only, never.

The API key is read once from ``get_settings().lever_api_key`` and used
only as the Basic Auth username (Lever's documented scheme — blank
password). It is never logged, never included in an exception message,
and never returned from any method.
"""

import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.lever.client import LeverClient
from app.integrations.lever.schemas import (
    LeverApplication,
    LeverArchiveReason,
    LeverInterview,
    LeverOfferSummary,
    LeverOpportunity,
    LeverPosting,
    LeverStage,
    LeverStageChange,
    LeverUser,
)

logger = logging.getLogger("app.integrations.lever.live_client")

_MAX_PAGE_SIZE = 100
_MAX_RETRIES = 3
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _parse_dt(epoch_ms: Any) -> Any:
    from datetime import UTC, datetime

    if not epoch_ms:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=UTC)
    except (TypeError, ValueError):
        return None


class LiveLeverClient(LeverClient):
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.lever_base_url.rstrip("/")
        self._auth = httpx.BasicAuth(settings.lever_api_key, "")
        self._timeout = httpx.Timeout(20.0, connect=10.0)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                with httpx.Client(auth=self._auth, timeout=self._timeout) as client:
                    resp = client.get(url, params=params or {})
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning("Lever GET timeout path=%s attempt=%s", path, attempt)
                time.sleep(0.5 * attempt)
                continue
            except httpx.HTTPError as exc:
                # Never include the response/request object (may carry the
                # Authorization header) in the log — category only.
                logger.warning("Lever GET transport error path=%s category=%s", path, type(exc).__name__)
                raise LeverApiError(f"Lever request failed: {type(exc).__name__}") from exc

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                logger.warning(
                    "Lever GET transient status=%s path=%s attempt=%s", resp.status_code, path, attempt
                )
                time.sleep(0.5 * attempt)
                continue
            raise LeverApiError(f"Lever GET {path} returned HTTP {resp.status_code}")

        raise LeverApiError(f"Lever GET {path} failed after {_MAX_RETRIES} attempts") from last_exc

    def _paginate(
        self, path: str, params: dict[str, Any] | None = None, max_items: int | None = None
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        query = dict(params or {})
        query.setdefault("limit", _MAX_PAGE_SIZE)
        offset = None
        while True:
            if offset is not None:
                query["offset"] = offset
            body = self._get(path, query)
            items.extend(body.get("data", []))
            if max_items is not None and len(items) >= max_items:
                return items[:max_items]
            if not body.get("hasNext"):
                break
            offset = body.get("next")
            if not offset:
                break
        return items

    # ---- read methods -----------------------------------------------

    def list_postings(self) -> list[LeverPosting]:
        rows = self._paginate("/postings")
        return [self._to_posting(r) for r in rows]

    def list_stages(self) -> list[LeverStage]:
        body = self._get("/stages")
        return [LeverStage(id=r["id"], text=r["text"]) for r in body.get("data", [])]

    def list_archive_reasons(self) -> list[LeverArchiveReason]:
        body = self._get("/archive_reasons")
        return [
            LeverArchiveReason(
                id=r["id"], text=r["text"], type=r.get("type"), status=r.get("status", "active")
            )
            for r in body.get("data", [])
        ]

    def list_users(self) -> list[LeverUser]:
        rows = self._paginate("/users")
        return [
            LeverUser(
                id=r["id"], name=r.get("name", ""), email=r.get("email", ""),
                access_role=r.get("accessRole", ""), deactivated=bool(r.get("deactivatedAt")),
            )
            for r in rows
        ]

    def list_opportunities(
        self, posting_id: str | None = None, limit: int | None = None
    ) -> list[LeverOpportunity]:
        params: dict[str, Any] = {}
        if posting_id is not None:
            params["posting_id"] = posting_id
        rows = self._paginate("/opportunities", params, max_items=limit)
        return [self._to_opportunity(r) for r in rows]

    def get_opportunity(self, opportunity_id: str) -> LeverOpportunity | None:
        body = self._get(f"/opportunities/{opportunity_id}")
        data = body.get("data")
        if not data:
            return None
        return self._to_opportunity(data)

    def list_applications(self, opportunity_id: str) -> list[LeverApplication]:
        rows = self._paginate(f"/opportunities/{opportunity_id}/applications")
        return [
            LeverApplication(
                id=r["id"], opportunity_id=r.get("opportunityId", opportunity_id),
                posting_id=r.get("posting"), posting_owner_user_id=r.get("postingOwner"),
                created_at=_parse_dt(r.get("createdAt")),
            )
            for r in rows
        ]

    def list_interviews(self, opportunity_id: str) -> list[LeverInterview]:
        rows = self._paginate(f"/opportunities/{opportunity_id}/interviews")
        return [
            LeverInterview(
                id=r["id"], opportunity_id=opportunity_id, subject=r.get("subject", ""),
                date=_parse_dt(r.get("date")) or _parse_dt(r.get("createdAt")),
                feedback_status=r.get("feedbackStatus", ""),
            )
            for r in rows
        ]

    def list_offers(self, opportunity_id: str) -> list[LeverOfferSummary]:
        """Status/lifecycle only — deliberately never reads compensation or
        document fields, even though Lever's response includes them."""
        rows = self._paginate(f"/opportunities/{opportunity_id}/offers")
        return [
            LeverOfferSummary(
                id=r["id"], posting_id=r.get("posting"), status=r.get("status", ""),
                created_at=_parse_dt(r.get("createdAt")),
            )
            for r in rows
        ]

    # ---- mapping helpers ----------------------------------------------

    @staticmethod
    def _to_posting(r: dict[str, Any]) -> LeverPosting:
        # `.get(key, "")` only substitutes the default when `key` is
        # *absent* — Lever's real API has been observed to return several
        # of these fields as explicit JSON `null` (present key, null
        # value), which `.get(key, "")` passes straight through, later
        # failing postings.<column> (all NOT NULL). `.get(key) or ""`
        # (already the pattern `department`/`hiring_manager_user_id` used
        # correctly below) normalizes both "absent" and "present but
        # null" to "". Found via a real second-sync idempotency check
        # against live data — mock fixtures never exercised a null value
        # here, so this shipped undetected until real data hit it.
        categories = r.get("categories") or {}
        return LeverPosting(
            id=r["id"], text=r.get("text") or "", state=r.get("state") or "",
            team=categories.get("team") or "", department=categories.get("department") or "",
            location=categories.get("location") or "", owner_user_id=r.get("owner") or "",
            hiring_manager_user_id=r.get("hiringManager") or "",
            confidentiality=r.get("confidentiality") or "", tags=list(r.get("tags", [])),
            archived=bool(r.get("archived")), created_at=_parse_dt(r.get("createdAt")),
            updated_at=_parse_dt(r.get("updatedAt")),
        )

    @staticmethod
    def _to_opportunity(r: dict[str, Any]) -> LeverOpportunity:
        stage_changes = [
            LeverStageChange(
                to_stage_id=sc.get("toStageId", ""), to_stage_index=sc.get("toStageIndex"),
                updated_at=_parse_dt(sc.get("updatedAt")), user_id=sc.get("userId"),
            )
            for sc in r.get("stageChanges", [])
        ]
        # Real Lever opportunities carry no direct posting field — only
        # `applications` (application ids). Confirmed by live discovery:
        # posting linkage lives on the Application sub-resource, not here.
        # Callers that need posting_id must resolve it via
        # ``list_applications(opportunity_id)`` and read `.posting_id`.
        return LeverOpportunity(
            id=r["id"], contact_id=r.get("contact", ""),
            name=r.get("name", ""), email=(r.get("emails") or [""])[0],
            headline=r.get("headline", ""), posting_id="",
            stage_id=r.get("stage", ""), stage_text="", archived=bool(r.get("archived")),
            created_at=_parse_dt(r.get("createdAt")), updated_at=_parse_dt(r.get("updatedAt")),
            tags=list(r.get("tags", [])), sources=list(r.get("sources", [])),
            owner_user_id=r.get("owner"), sourced_by_user_id=r.get("sourcedBy"),
            archive_reason_id=(
                r["archived"].get("reason") if isinstance(r.get("archived"), dict) else None
            ),
            application_ids=list(r.get("applications", [])), stage_changes=stage_changes,
        )


class LeverApiError(Exception):
    """Raised on any non-200, non-retryable Lever response, or after
    exhausting retries on a transient failure. Never carries the API key
    or raw request/response objects."""
