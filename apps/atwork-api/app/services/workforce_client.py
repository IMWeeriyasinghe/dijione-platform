"""Read-only client for people-api's Workforce Directory.

Resolves Client (= BambooHR department) for a set of work emails.
Results are cached in-process for CACHE_TTL_SECONDS.
"""
from __future__ import annotations

import logging
import time

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.employee_directory import employee_names

logger = logging.getLogger("atwork-api.workforce_client")

CACHE_TTL_SECONDS = 300  # 5 minutes
UNASSIGNED = ""

_cache: tuple[float, dict[str, str]] | None = None  # (expires, email->department)


def _fetch_email_to_dept(emails: list[str]) -> dict[str, str]:
    if not emails:
        return {}
    settings = get_settings()
    try:
        resp = httpx.post(
            f"{settings.people_api_url}/api/people/workforce-directory/email-enrich",
            json={"emails": emails},
            headers={"X-Internal-Service-Secret": settings.internal_service_secret},
            timeout=settings.people_api_timeout_seconds,
        )
        resp.raise_for_status()
        return {row["work_email"].lower(): row["department"] for row in resp.json() if row.get("work_email")}
    except Exception:
        logger.warning("Workforce email-enrich failed — client fields unavailable", exc_info=False)
        return {}


def _get_cache() -> dict[str, str] | None:
    global _cache
    if _cache and time.monotonic() < _cache[0]:
        return _cache[1]
    return None


def _set_cache(data: dict[str, str]) -> None:
    global _cache
    _cache = (time.monotonic() + CACHE_TTL_SECONDS, data)


def resolve_client_for_users(db: Session, user_ids: set[int]) -> dict[int, str]:
    """platform_user_id → client name (= BambooHR department).

    Returns empty string for employees with no directory match.
    """
    if not user_ids:
        return {}

    names = employee_names(db, user_ids)
    emails = {(emp.email or "").strip().lower() for emp in names.values() if emp.email}

    if not emails:
        return {uid: UNASSIGNED for uid in user_ids}

    cached = _get_cache()
    if cached is not None:
        email_to_dept = cached
    else:
        email_to_dept = _fetch_email_to_dept(list(emails))
        _set_cache(email_to_dept)

    result: dict[int, str] = {}
    for uid, emp in names.items():
        if uid in user_ids:
            email = (emp.email or "").strip().lower()
            result[uid] = email_to_dept.get(email, UNASSIGNED)
    for uid in user_ids:
        if uid not in result:
            result[uid] = UNASSIGNED
    return result
