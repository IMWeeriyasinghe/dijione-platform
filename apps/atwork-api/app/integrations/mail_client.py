"""Email client factory for atwork-api reminder emails.

Mirrors the birthday-api factory pattern: transport is cached (preserves
Graph token), policy is not (allowlist changes should not need a restart).
"""

from __future__ import annotations

from functools import lru_cache

from mail_client_py import (
    GraphMailTransport,
    InternalAllowlistPolicy,
    MailClient,
    MailPolicy,
    MailTransport,
    NullMailTransport,
    ProductionPolicy,
)

from app.core.config import get_settings


@lru_cache
def _get_transport() -> MailTransport:
    settings = get_settings()
    if settings.mail_transport == "graph":
        return GraphMailTransport(
            sender_mailbox=settings.mail_shared_mailbox,
            base_url=settings.graph_base_url,
        )
    return NullMailTransport()


def _build_policy() -> MailPolicy:
    settings = get_settings()
    if settings.mail_policy == "production":
        return ProductionPolicy()
    if settings.mail_policy == "internal_allowlist":
        allowlist = [a.strip() for a in settings.mail_allowlist.split(",") if a.strip()]
        return InternalAllowlistPolicy(allowlist)
    from mail_client_py import DisabledPolicy

    return DisabledPolicy()


def get_mail_client() -> MailClient:
    return MailClient(transport=_get_transport(), policy=_build_policy())
