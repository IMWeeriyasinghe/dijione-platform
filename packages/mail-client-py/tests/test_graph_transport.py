"""GraphMailTransport tests — mocked httpx + mocked credential, no real
network, no real Azure identity. Asserts the single sendMail call shape
(Mail.Send-only permission surface — no draft-create call is ever made)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mail_client_py import GraphTransportNotConfiguredError
from mail_client_py.graph_transport import GraphMailTransport
from mail_client_py.transport import MailOutcome


def _fake_credential(token="fake-token", expires_in=3600):
    cred = MagicMock()
    cred.get_token.return_value = SimpleNamespace(token=token, expires_on=__import__("time").time() + expires_in)
    return cred


def test_requires_sender_mailbox():
    with pytest.raises(GraphTransportNotConfiguredError):
        GraphMailTransport(sender_mailbox="")


@patch("mail_client_py.graph_transport.DefaultAzureCredential")
@patch("mail_client_py.graph_transport.httpx.post")
def test_success_202_reports_submitted(mock_post, mock_cred_cls):
    mock_cred_cls.return_value = _fake_credential()
    mock_post.return_value = httpx.Response(202, headers={"request-id": "diag-123"}, request=httpx.Request("POST", "https://x"))

    transport = GraphMailTransport(sender_mailbox="appassistant@dijitalteam.com")
    result = transport.send(to="a@b.com", subject="s", body="b", correlation_id="corr-1")

    assert result.outcome == MailOutcome.SUBMITTED
    assert result.sent is True
    assert result.correlation_id == "corr-1"
    assert result.graph_request_id == "diag-123"

    # Exactly one call — the single sendMail request, never a draft-create.
    assert mock_post.call_count == 1
    called_url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url")
    assert called_url.endswith("/users/appassistant@dijitalteam.com/sendMail")


@pytest.mark.parametrize("status", [401, 403, 429, 500])
@patch("mail_client_py.graph_transport.DefaultAzureCredential")
@patch("mail_client_py.graph_transport.httpx.post")
def test_failure_statuses_report_failed(mock_post, mock_cred_cls, status):
    mock_cred_cls.return_value = _fake_credential()
    mock_post.return_value = httpx.Response(status, text="error", request=httpx.Request("POST", "https://x"))

    transport = GraphMailTransport(sender_mailbox="appassistant@dijitalteam.com")
    result = transport.send(to="a@b.com", subject="s", body="b", correlation_id="corr-2")

    assert result.outcome == MailOutcome.FAILED
    assert result.sent is False
    assert result.correlation_id == "corr-2"
    assert result.error


@patch("mail_client_py.graph_transport.DefaultAzureCredential")
def test_credential_failure_reports_failed_not_an_unhandled_exception(mock_cred_cls):
    cred = MagicMock()
    cred.get_token.side_effect = Exception("no managed identity available")
    mock_cred_cls.return_value = cred

    transport = GraphMailTransport(sender_mailbox="appassistant@dijitalteam.com")
    result = transport.send(to="a@b.com", subject="s", body="b", correlation_id="corr-3")

    assert result.outcome == MailOutcome.FAILED
    assert result.sent is False
    assert "managed identity" in (result.error or "").lower()
