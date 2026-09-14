"""No-network transport — the safe local/CI default. Truthfully reports
SIMULATED, never SUBMITTED: no real email is ever submitted anywhere by
this transport, and the shared contract must never claim otherwise."""

from __future__ import annotations

import logging

from mail_client_py.transport import MailOutcome, MailResult, MailTransport

logger = logging.getLogger(__name__)


class NullMailTransport(MailTransport):
    def send(self, *, to: str, subject: str, body: str, correlation_id: str) -> MailResult:
        if not to:
            # The deliberate hook consuming services use to simulate a
            # failed send (e.g. missing/invalid recipient) without real
            # transport credentials.
            logger.warning("NullMailTransport: no recipient — correlation_id=%s", correlation_id)
            return MailResult(
                correlation_id=correlation_id, outcome=MailOutcome.FAILED, sent=False,
                error="no recipient",
            )

        logger.info(
            "NullMailTransport: simulated send to %s (subject=%r, correlation_id=%s)",
            to, subject, correlation_id,
        )
        return MailResult(correlation_id=correlation_id, outcome=MailOutcome.SIMULATED, sent=False)
