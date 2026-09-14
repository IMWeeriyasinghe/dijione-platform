import logging
from functools import lru_cache

from mail_client_py import (
    DisabledPolicy,
    GraphMailTransport,
    InternalAllowlistPolicy,
    MailClient,
    MailPolicy,
    MailTransport,
    NullMailTransport,
    ProductionPolicy,
)
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.people_source.client import EmployeeSourceClient
from app.integrations.people_source.mock_adapter import MockEmployeeSource

logger = logging.getLogger(__name__)


@lru_cache
def get_employee_source() -> EmployeeSourceClient:
    """birthday-api holds NO BambooHR credential (Architecture Completion
    Plan §3) — it consumes the People / Workforce domain (people-api) over
    HTTP. Mock by default; the real adapter calls people-api."""
    settings = get_settings()
    if settings.integrations_mode == "mock":
        return MockEmployeeSource()
    from app.integrations.people_source.http_adapter import PeopleApiEmployeeSource

    return PeopleApiEmployeeSource()


@lru_cache
def _get_transport() -> MailTransport:
    """The transport half of get_email_client() — safe to cache (unlike
    the policy half, below): which mailbox/credential birthday-api sends
    through never changes at runtime, and caching GraphMailTransport
    across calls preserves its in-memory Graph token cache instead of
    re-authenticating on every send."""
    settings = get_settings()
    if settings.mail_transport == "graph":
        return GraphMailTransport(
            sender_mailbox=settings.mail_shared_mailbox, base_url=settings.graph_base_url,
        )
    return NullMailTransport()


def _build_policy(db: Session | None) -> MailPolicy:
    """Deliberately NOT cached — unlike the transport, the policy for
    "internal_allowlist" must reflect BirthdayTestEmailRecipient's live DB
    state on every call, with no redeploy/restart, per the explicit
    runtime-administration requirement (docs/platform/email-architecture.md).

    NullMailTransport can never submit a real email regardless of policy,
    so pairing it with a permissive policy is safe and keeps
    business-workflow testing working exactly as before — policy only
    carries real weight once mail_transport=graph is actually in play.
    """
    settings = get_settings()
    if settings.mail_transport != "graph":
        return ProductionPolicy()

    if settings.mail_policy != "internal_allowlist":
        # "disabled" (fail-closed default) or "production" (real
        # supplier traffic — the DB-backed test allowlist must never
        # restrict it, per the explicit PROD-behavior requirement).
        return ProductionPolicy() if settings.mail_policy == "production" else DisabledPolicy()

    if db is None:
        # A caller reached the graph+internal_allowlist path without a DB
        # session to query — fail closed rather than silently falling
        # back to an open policy.
        logger.warning("mail_policy=internal_allowlist requested with no db session — failing closed")
        return DisabledPolicy()

    try:
        from app.services.test_email_recipient_service import list_active_recipient_emails

        allowlist = list_active_recipient_emails(db)
    except Exception:  # noqa: BLE001 - a DB lookup failure must fail closed, never silently allow
        logger.exception("Failed to load the test-email-recipient allowlist — failing closed")
        return DisabledPolicy()

    return InternalAllowlistPolicy(allowlist)


def get_email_client(db: Session | None = None) -> MailClient:
    """The one place birthday-api builds its outbound MailClient — binds
    the shared, transport-agnostic packages/mail-client-py library to this
    service's own config (mail_transport/mail_policy/mail_shared_mailbox)
    plus, for mail_policy="internal_allowlist", the live
    BirthdayTestEmailRecipient table (db must be passed by every caller on
    the outbound-send path — see app/services/order_email_service.py).
    mail_transport (not email_sending_mode, which now gates inbound only)
    decides null vs. graph."""
    return MailClient(transport=_get_transport(), policy=_build_policy(db))


@lru_cache
def get_inbound_mail_client():
    """Inbound supplier-mail poll transport (Phase 1 §1.5) — untouched by
    the outbound Managed Identity migration, still gated by
    ``email_sending_mode``. DEV stays mock (the dev inject endpoint drives
    the pipeline)."""
    settings = get_settings()
    if settings.email_sending_mode == "mock":
        from app.integrations.inbound_mail.mock_client import MockInboundMailClient

        return MockInboundMailClient()
    from app.integrations.inbound_mail.graph_client import GraphInboundMailClient

    return GraphInboundMailClient()
