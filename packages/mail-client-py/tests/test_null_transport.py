from mail_client_py import MailOutcome, NullMailTransport


def test_successful_simulated_send_reports_simulated_not_submitted():
    transport = NullMailTransport()
    result = transport.send(to="someone@example.com", subject="s", body="b", correlation_id="c1")

    assert result.outcome == MailOutcome.SIMULATED
    # Truthful contract: sent is False even on the would-succeed path,
    # since no real email left the system.
    assert result.sent is False
    assert result.correlation_id == "c1"


def test_empty_recipient_reports_failed():
    transport = NullMailTransport()
    result = transport.send(to="", subject="s", body="b", correlation_id="c2")

    assert result.outcome == MailOutcome.FAILED
    assert result.sent is False
    assert result.correlation_id == "c2"
    assert result.error
