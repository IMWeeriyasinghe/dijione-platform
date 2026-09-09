"""Real Microsoft Graph inbound-mail adapter (polling, §H.0) — not
exercised against real endpoints in DEV (no credentials). Reads the shared
mailbox's Inbox filtered by ``receivedDateTime`` above the poll watermark,
oldest first. OAuth2 client-credentials, same app registration as outbound
email plus the ``Mail.Read`` (application) permission (UAT gate §H.4).
"""

from __future__ import annotations

import time
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.integrations.inbound_mail.client import (
    InboundMailClient,
    InboundMailNotConfiguredError,
    InboundMessage,
)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SCOPE = "https://graph.microsoft.com/.default"
_MARGIN_S = 60


def _header_values(headers: list[dict] | None, name: str) -> list[str]:
    out: list[str] = []
    for h in headers or []:
        if (h.get("name") or "").lower() == name.lower():
            raw = h.get("value") or ""
            out.extend(part.strip("<> \t") for part in raw.replace(",", " ").split() if part.strip())
    return out


class GraphInboundMailClient(InboundMailClient):
    def __init__(self):
        s = get_settings()
        if not (s.graph_tenant_id and s.graph_client_id and s.graph_client_secret and s.graph_inbox_mailbox):
            raise InboundMailNotConfiguredError(
                "Inbound mail is not configured — graph_tenant_id, graph_client_id, "
                "graph_client_secret and graph_inbox_mailbox must all be set. "
                "Set EMAIL_SENDING_MODE=mock to use MockInboundMailClient."
            )
        self._tenant = s.graph_tenant_id
        self._client_id = s.graph_client_id
        self._secret = s.graph_client_secret
        self._mailbox = s.graph_inbox_mailbox
        self._base = s.graph_base_url
        self._token: str | None = None
        self._exp = 0.0

    def _access_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._exp:
            return self._token
        r = httpx.post(
            _TOKEN_URL.format(tenant=self._tenant),
            data={
                "grant_type": "client_credentials", "client_id": self._client_id,
                "client_secret": self._secret, "scope": _SCOPE,
            },
            timeout=10.0,
        )
        r.raise_for_status()
        p = r.json()
        self._token = p["access_token"]
        self._exp = now + p.get("expires_in", 3600) - _MARGIN_S
        return self._token

    def list_messages_since(self, watermark: datetime | None, *, limit: int = 50) -> list[InboundMessage]:
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        params = {
            "$orderby": "receivedDateTime asc",
            "$top": str(min(limit, 50)),
            "$select": "id,subject,from,receivedDateTime,body,hasAttachments,internetMessageHeaders",
        }
        if watermark is not None:
            params["$filter"] = f"receivedDateTime gt {watermark.astimezone().isoformat()}"
        url = f"{self._base}/users/{self._mailbox}/mailFolders/inbox/messages"
        resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
        resp.raise_for_status()

        out: list[InboundMessage] = []
        for m in resp.json().get("value", []):
            body = m.get("body") or {}
            hdrs = m.get("internetMessageHeaders")
            out.append(
                InboundMessage(
                    id=m["id"],
                    from_address=((m.get("from") or {}).get("emailAddress") or {}).get("address", ""),
                    subject=m.get("subject") or "",
                    body_text=body.get("content") or "",
                    received_at=datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00"))
                    if m.get("receivedDateTime") else None,
                    in_reply_to=_header_values(hdrs, "In-Reply-To"),
                    references=_header_values(hdrs, "References"),
                    attachment_count=1 if m.get("hasAttachments") else 0,
                )
            )
        return out
