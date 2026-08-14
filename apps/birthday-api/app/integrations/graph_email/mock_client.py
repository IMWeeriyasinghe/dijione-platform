"""No-network mock — default dev/test email client, lets Phases B-D be
built/tested before Graph app registration/consent lands (plan §9)."""

import logging
from uuid import uuid4

from app.integrations.graph_email.client import EmailClient
from app.integrations.graph_email.schemas import EmailSendResult

logger = logging.getLogger(__name__)


class MockGraphEmailClient(EmailClient):
    def send(self, *, to: str, subject: str, body: str, order_reference: str) -> EmailSendResult:
        message_id = f"mock-msg-{uuid4()}"
        if not to:
            # Simulate a failed send (e.g. missing/invalid recipient) so the
            # failure path (REQUIRES_ATTENTION + EMAIL_FAILED + admin
            # notification) is exercisable without real Graph credentials.
            logger.warning(
                "MockGraphEmailClient: send failed for order %s — no recipient", order_reference
            )
            return EmailSendResult(message_id=message_id, sent=False)

        logger.info(
            "MockGraphEmailClient: sent order %s to %s (subject=%r, message_id=%s)",
            order_reference, to, subject, message_id,
        )
        return EmailSendResult(message_id=message_id, sent=True)
