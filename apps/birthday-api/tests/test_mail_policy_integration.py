"""Mail-policy integration (app/integrations/factory.py's _build_policy +
get_email_client) — proves the DB-backed Email Safety allowlist actually
gates the transport for mail_policy=internal_allowlist, fails closed on a
DB error, and never restricts mail_policy=production. See
docs/platform/email-architecture.md.
"""

from __future__ import annotations

from mail_client_py import MailOutcome
from mail_client_py.transport import MailResult

from app.core.config import get_settings
from app.integrations import factory
from app.services.test_email_recipient_service import create_recipient


class _ProbeTransport:
    """A fake MailTransport — records whether/how many times it was
    invoked, so tests can prove the transport is never reached when the
    policy blocks/disables."""

    def __init__(self):
        self.calls = []

    def send(self, *, to, subject, body, correlation_id, content_type="Text"):
        self.calls.append(to)
        return MailResult(correlation_id=correlation_id, outcome=MailOutcome.SUBMITTED, sent=True)


class _FailingSession:
    """Stands in for `db` to force the allowlist lookup to raise, proving
    _build_policy fails closed (DisabledPolicy) rather than silently
    allowing the send."""

    def execute(self, *args, **kwargs):
        raise RuntimeError("simulated DB failure")


def _configure(monkeypatch, *, mail_transport="graph", mail_policy="internal_allowlist"):
    monkeypatch.setenv("MAIL_TRANSPORT", mail_transport)
    monkeypatch.setenv("MAIL_POLICY", mail_policy)
    monkeypatch.setenv("MAIL_SHARED_MAILBOX", "appassistant@dijitalteam.com")
    get_settings.cache_clear()
    probe = _ProbeTransport()
    monkeypatch.setattr(factory, "_get_transport", lambda: probe)
    return probe


def teardown_function(_fn):
    get_settings.cache_clear()


def test_approved_internal_recipient_allowed(db, monkeypatch):
    probe = _configure(monkeypatch)
    create_recipient(
        db, email_address="madushanka.weeriyasinghe@dijitalteam.com", display_label="",
        recipient_type="INTERNAL_TESTER", is_active=True, actor_id=None,
    )
    db.commit()

    client = factory.get_email_client(db)
    result = client.send(to="madushanka.weeriyasinghe@dijitalteam.com", subject="s", body="b")

    assert result.outcome == MailOutcome.SUBMITTED
    assert probe.calls == ["madushanka.weeriyasinghe@dijitalteam.com"]


def test_approved_gmail_test_supplier_allowed(db, monkeypatch):
    probe = _configure(monkeypatch)
    create_recipient(
        db, email_address="madusankaweeriyasinghe20@gmail.com", display_label="",
        recipient_type="TEST_SUPPLIER", is_active=True, actor_id=None,
    )
    db.commit()

    client = factory.get_email_client(db)
    result = client.send(to="madusankaweeriyasinghe20@gmail.com", subject="s", body="b")

    assert result.outcome == MailOutcome.SUBMITTED
    assert probe.calls == ["madusankaweeriyasinghe20@gmail.com"]


def test_unknown_recipient_blocked_before_transport(db, monkeypatch):
    probe = _configure(monkeypatch)

    client = factory.get_email_client(db)
    result = client.send(to="random-external@example.com", subject="s", body="b")

    assert result.outcome == MailOutcome.BLOCKED
    assert result.sent is False
    assert probe.calls == []


def test_inactive_recipient_blocked(db, monkeypatch):
    probe = _configure(monkeypatch)
    create_recipient(
        db, email_address="was.active@dijitalteam.com", display_label="", recipient_type="INTERNAL_TESTER",
        is_active=False, actor_id=None,
    )
    db.commit()

    client = factory.get_email_client(db)
    result = client.send(to="was.active@dijitalteam.com", subject="s", body="b")

    assert result.outcome == MailOutcome.BLOCKED
    assert probe.calls == []


def test_case_insensitive_and_whitespace_normalized_match(db, monkeypatch):
    probe = _configure(monkeypatch)
    create_recipient(
        db, email_address="Madushanka.Weeriyasinghe@dijitalteam.com", display_label="",
        recipient_type="INTERNAL_TESTER", is_active=True, actor_id=None,
    )
    db.commit()

    client = factory.get_email_client(db)
    result = client.send(to="  madushanka.weeriyasinghe@DIJITALTEAM.com  ", subject="s", body="b")

    assert result.outcome == MailOutcome.SUBMITTED
    assert probe.calls


def test_transport_invoked_only_after_policy_pass(db, monkeypatch):
    probe = _configure(monkeypatch)
    client = factory.get_email_client(db)

    client.send(to="blocked@example.com", subject="s", body="b")
    assert probe.calls == []

    create_recipient(
        db, email_address="blocked@example.com", display_label="", recipient_type="INTERNAL_TESTER",
        is_active=True, actor_id=None,
    )
    db.commit()
    client = factory.get_email_client(db)
    client.send(to="blocked@example.com", subject="s", body="b")
    assert probe.calls == ["blocked@example.com"]


def test_db_failure_fails_closed(monkeypatch):
    probe = _configure(monkeypatch)

    client = factory.get_email_client(_FailingSession())
    result = client.send(to="anyone@dijitalteam.com", subject="s", body="b")

    assert result.outcome == MailOutcome.DISABLED
    assert probe.calls == []


def test_production_policy_does_not_require_test_recipient_record(db, monkeypatch):
    probe = _configure(monkeypatch, mail_policy="production")

    client = factory.get_email_client(db)
    result = client.send(to="real.supplier@example.com", subject="s", body="b")

    assert result.outcome == MailOutcome.SUBMITTED
    assert probe.calls == ["real.supplier@example.com"]
