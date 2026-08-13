"""Typed HTTP client for Platform Core's internal write surface
(``/api/platform/internal/*`` and, for admin-api, ``/api/platform/admin/*``).

Used by talent-api (and, once implemented, birthday-api/spark-api) to record
audit events and create notifications instead of writing to Platform Core's
tables directly — AuditLog and Notification are platform-owned (CR §27).

Every method here is **best-effort and non-fatal by design**: a business
action (approving a talent request, scheduling an interview) must not fail
just because Platform Core is briefly unavailable. Failures are logged and
swallowed, never raised — see docs/platform/failure-isolation.md. Callers
that genuinely need the platform-admin surface (admin-api) should use
``request_admin`` directly and propagate its response, since that path is a
live pass-through of a real admin action, not a fire-and-forget side effect.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("dijione.platform_client")


class PlatformClient:
    def __init__(
        self,
        base_url: str,
        internal_secret: str,
        timeout: float = 5.0,
        *,
        client: httpx.Client | None = None,
    ):
        """``client`` lets tests inject an ``httpx.Client`` bound to an
        ``ASGITransport`` (a real in-process FastAPI app, no sockets) instead
        of making real network calls — used by admin-api's contract tests to
        exercise a real platform-api app. Production code should leave it
        unset."""
        self._base_url = base_url.rstrip("/")
        self._internal_secret = internal_secret
        self._timeout = timeout
        self._client = client

    # --- Best-effort service-to-service writes ---------------------------

    def record_audit_event(
        self,
        *,
        actor_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int,
        previous_state: dict | str | None = None,
        new_state: dict | str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        return self._post_internal(
            "/api/platform/internal/audit-events",
            {
                "actor_id": actor_id, "action": action, "entity_type": entity_type,
                "entity_id": entity_id, "previous_state": previous_state,
                "new_state": new_state, "metadata": metadata,
            },
        )

    def notify_user(
        self,
        *,
        user_id: int,
        type: str,
        title: str,
        body: str = "",
        related_entity_type: str | None = None,
        related_entity_id: int | None = None,
    ) -> bool:
        return self._post_internal(
            "/api/platform/internal/notifications",
            {
                "user_id": user_id, "type": type, "title": title, "body": body,
                "related_entity_type": related_entity_type, "related_entity_id": related_entity_id,
            },
        )

    def broadcast_notification(
        self,
        *,
        module_key: str,
        role: str,
        type: str,
        title: str,
        body: str = "",
        related_entity_type: str | None = None,
        related_entity_id: int | None = None,
        client_id: int | None = None,
    ) -> bool:
        return self._post_internal(
            "/api/platform/internal/notifications/broadcast",
            {
                "module_key": module_key, "role": role, "type": type, "title": title, "body": body,
                "related_entity_type": related_entity_type, "related_entity_id": related_entity_id,
                "client_id": client_id,
            },
        )

    def _post_internal(self, path: str, payload: dict) -> bool:
        try:
            resp = self._request(
                "POST", path, headers={"X-Internal-Token": self._internal_secret}, json=payload
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning("Platform Core call to %s failed (non-fatal): %s", path, exc)
            return False

    def get_internal(self, path: str, *, params: dict | None = None) -> httpx.Response:
        """Best-effort internal GET (e.g. talent-api's clients-lite/summary
        endpoints). Raises ``httpx.HTTPError`` — callers decide whether a
        failure here is fatal to the request they're serving."""
        resp = self._request(
            "GET", path, headers={"X-Internal-Token": self._internal_secret}, params=params
        )
        resp.raise_for_status()
        return resp

    # --- Live pass-through for human-initiated admin actions -------------

    def request_admin(
        self, method: str, path: str, *, bearer_token: str, json: dict | None = None, params: dict | None = None
    ) -> httpx.Response:
        """Forward an admin-api request to Platform Core's
        ``/api/platform/admin/*`` surface with the *original caller's*
        bearer token — Platform Core re-derives the actor's permissions from
        that token itself (CR §48: never trust another service's word for
        who is calling). Raises ``httpx.HTTPError`` on a connection failure;
        admin-api is expected to translate that into a 502/503, not swallow
        it, since this is a live user-facing action, not a background
        side effect.
        """
        return self._request(
            method, path, headers={"Authorization": f"Bearer {bearer_token}"}, json=json, params=params
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._client is not None:
            # An injected test client (e.g. starlette's TestClient) doesn't
            # accept a per-call `timeout` override — it's already bound to
            # an in-process ASGI app with no real network latency.
            return self._client.request(method, path, **kwargs)
        return httpx.request(method, f"{self._base_url}{path}", timeout=self._timeout, **kwargs)
