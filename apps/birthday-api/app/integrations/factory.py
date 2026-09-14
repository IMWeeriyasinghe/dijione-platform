from functools import lru_cache

from mail_client_py import GraphMailTransport, MailClient, NullMailTransport, ProductionPolicy, resolve_policy

from app.core.config import get_settings
from app.integrations.people_source.client import EmployeeSourceClient
from app.integrations.people_source.mock_adapter import MockEmployeeSource


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
def get_email_client() -> MailClient:
    """The one place birthday-api builds its outbound MailClient — binds
    the shared, transport-agnostic packages/mail-client-py library to this
    service's own config (mail_transport/mail_policy/mail_shared_mailbox/
    mail_allowlist). mail_transport (not email_sending_mode, which now
    gates inbound only) decides null vs. graph.

    mail_policy (default "disabled" — fail closed) only matters once a
    real transport is actually in play: NullMailTransport can never submit
    a real email regardless of policy, so gating it too would only break
    business-workflow testing for no safety benefit — birthday-api's own
    judgment call, made here rather than in the shared library (which
    stays fully generic and applies whatever policy it's given uniformly,
    exactly as designed). The moment mail_transport=graph is turned on,
    mail_policy's real, fail-closed-by-default value governs — an operator
    who forgets to also set it still gets DISABLED, never an accidental
    open send."""
    settings = get_settings()

    if settings.mail_transport == "graph":
        transport = GraphMailTransport(
            sender_mailbox=settings.mail_shared_mailbox, base_url=settings.graph_base_url,
        )
        policy = resolve_policy(settings.mail_policy, allowlist=settings.mail_allowlist_list)
    else:
        transport = NullMailTransport()
        policy = ProductionPolicy()

    return MailClient(transport=transport, policy=policy)


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
