"""Real Microsoft Graph email adapter — not exercised by tests against real
endpoints (no credentials available). Implements the create-draft-then-send
sequence (plan §9):

1. ``POST /users/{mailbox}/messages`` — create draft, capture Graph ``id``.
2. ``POST /users/{mailbox}/messages/{id}/send`` — send that exact draft.

OAuth2 client-credentials flow against
``https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token``,
scope ``https://graph.microsoft.com/.default``, with a simple in-memory
cached token (expiry-checked, re-fetched when stale).
"""

from __future__ import annotations

import time

import httpx

from app.core.config import get_settings
from app.integrations.graph_email.client import EmailClient, GraphNotConfiguredError
from app.integrations.graph_email.schemas import EmailSendResult

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
# Refresh a little before actual expiry to avoid racing a request against it.
_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60


class GraphEmailClient(EmailClient):
    def __init__(self):
        settings = get_settings()
        if not (
            settings.graph_tenant_id
            and settings.graph_client_id
            and settings.graph_client_secret
            and settings.graph_sender_mailbox
        ):
            raise GraphNotConfiguredError(
                "Microsoft Graph is not configured — graph_tenant_id, graph_client_id, "
                "graph_client_secret, and graph_sender_mailbox must all be set. Set "
                "INTEGRATIONS_MODE=mock to continue using MockGraphEmailClient."
            )
        self._tenant_id = settings.graph_tenant_id
        self._client_id = settings.graph_client_id
        self._client_secret = settings.graph_client_secret
        self._sender_mailbox = settings.graph_sender_mailbox
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0

    def _get_access_token(self) -> str:
        now = time.monotonic()
        if self._cached_token and now < self._token_expires_at:
            return self._cached_token

        token_url = _TOKEN_URL_TEMPLATE.format(tenant_id=self._tenant_id)
        response = httpx.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": _GRAPH_SCOPE,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        self._cached_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        self._token_expires_at = now + expires_in - _TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS
        return self._cached_token

    def send(self, *, to: str, subject: str, body: str, order_reference: str) -> EmailSendResult:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Step 1: create the draft, capture the Graph message id.
        draft_payload = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        create_resp = httpx.post(
            f"{GRAPH_BASE_URL}/users/{self._sender_mailbox}/messages",
            headers=headers,
            json=draft_payload,
            timeout=10.0,
        )
        create_resp.raise_for_status()
        message_id = create_resp.json()["id"]

        # Step 2: send that exact draft.
        send_resp = httpx.post(
            f"{GRAPH_BASE_URL}/users/{self._sender_mailbox}/messages/{message_id}/send",
            headers=headers,
            timeout=10.0,
        )
        send_resp.raise_for_status()

        return EmailSendResult(message_id=message_id, sent=True)
