"""MailClient orchestration tests — the structural "block before Graph"
guarantee, sender non-overridability, and correlation-id presence on
every outcome."""

from __future__ import annotations

from mail_client_py.client import MailClient
from mail_client_py.policy import DisabledPolicy, InternalAllowlistPolicy, ProductionPolicy
from mail_client_py.transport import MailOutcome, MailResult, MailTransport


class _CountingTransport(MailTransport):
    def __init__(self):
        self.call_count = 0

    def send(self, *, to, subject, body, correlation_id, content_type="Text"):
        self.call_count += 1
        return MailResult(correlation_id=correlation_id, outcome=MailOutcome.SUBMITTED, sent=True)


def test_disabled_policy_never_invokes_transport():
    transport = _CountingTransport()
    client = MailClient(transport=transport, policy=DisabledPolicy())

    result = client.send(to="anyone@example.com", subject="s", body="b")

    assert transport.call_count == 0
    assert result.outcome == MailOutcome.DISABLED
    assert result.sent is False
    assert result.correlation_id  # present even when blocked


def test_blocked_recipient_never_invokes_transport():
    transport = _CountingTransport()
    client = MailClient(transport=transport, policy=InternalAllowlistPolicy(["test@dijitalteam.com"]))

    result = client.send(to="external@supplier.example.com", subject="s", body="b")

    assert transport.call_count == 0
    assert result.outcome == MailOutcome.BLOCKED
    assert result.sent is False
    assert result.correlation_id


def test_allowed_recipient_invokes_transport():
    transport = _CountingTransport()
    client = MailClient(transport=transport, policy=InternalAllowlistPolicy(["test@dijitalteam.com"]))

    result = client.send(to="test@dijitalteam.com", subject="s", body="b")

    assert transport.call_count == 1
    assert result.outcome == MailOutcome.SUBMITTED
    assert result.sent is True


def test_production_policy_invokes_transport():
    transport = _CountingTransport()
    client = MailClient(transport=transport, policy=ProductionPolicy())

    client.send(to="anyone@example.com", subject="s", body="b")

    assert transport.call_count == 1


def test_correlation_id_generated_when_not_supplied():
    transport = _CountingTransport()
    client = MailClient(transport=transport, policy=ProductionPolicy())

    result = client.send(to="a@b.com", subject="s", body="b")

    assert result.correlation_id


def test_caller_supplied_correlation_id_is_preserved():
    transport = _CountingTransport()
    client = MailClient(transport=transport, policy=ProductionPolicy())

    result = client.send(to="a@b.com", subject="s", body="b", correlation_id="my-own-id")

    assert result.correlation_id == "my-own-id"


def test_send_has_no_sender_override_parameter():
    # Structural check: MailClient.send() accepts no `from`/`sender`
    # parameter at all — sender sanitization is enforced by the absence
    # of the parameter, not by runtime validation.
    import inspect

    params = inspect.signature(MailClient.send).parameters
    assert "from_" not in params and "sender" not in params and "from_address" not in params
