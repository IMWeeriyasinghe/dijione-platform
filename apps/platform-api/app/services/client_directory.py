"""Temporary guard: resolve DijiTalentFlow client ids against talent-api.

Until the Commercial / CRM canonical client identity exists (Data Ownership
Architecture v2 §6/§9), ``platform-api``'s client-scope ``client_id`` values are
bare integers *assumed* to match ``talent-api``'s ``clients.id`` — with no
foreign key and (previously) no runtime check. A divergence between the two
databases silently pointed a staff portfolio at the wrong organisations.

This helper makes that mismatch loud instead of silent:

* at assignment time — reject a scope that names an unknown client id;
* in ``/health/deep`` — flag any already-stored orphan scope ids.

It calls talent-api's existing ``GET /api/talent/internal/clients-lite``
(``X-Internal-Token`` gated) — the same internal contract admin-api already
uses. It is deliberately *fail-safe*: if talent-api cannot be reached, the
caller should refuse the write rather than persist an unvalidated id.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings


class ClientDirectoryUnavailableError(Exception):
    """talent-api's clients-lite endpoint could not be reached to validate ids."""


class UnknownClientIdError(Exception):
    """One or more supplied client ids do not exist in talent-api."""

    def __init__(self, unknown: list[int]) -> None:
        self.unknown = unknown
        super().__init__(f"Unknown DijiTalentFlow client id(s): {unknown}")


def known_client_ids() -> set[int]:
    settings = get_settings()
    resp = httpx.get(
        f"{settings.talent_api_url}/api/talent/internal/clients-lite",
        headers={"X-Internal-Token": settings.internal_service_secret},
        timeout=3.0,
    )
    resp.raise_for_status()
    return {int(row["id"]) for row in resp.json()}


def validate_client_ids(client_ids: list[int] | set[int]) -> None:
    """Raise ``UnknownClientIdError`` if any id is not a real talent-api client,
    or ``ClientDirectoryUnavailableError`` if talent-api is unreachable. A no-op
    for an empty set."""
    wanted = {int(c) for c in client_ids}
    if not wanted:
        return
    try:
        known = known_client_ids()
    except httpx.HTTPError as exc:  # connect error, timeout, non-2xx
        raise ClientDirectoryUnavailableError(str(exc)) from exc
    unknown = sorted(wanted - known)
    if unknown:
        raise UnknownClientIdError(unknown)
