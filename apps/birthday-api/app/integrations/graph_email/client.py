"""EmailClient interface — ABC+mock+factory shape mirroring
``app/integrations/bamboohr/client.py``. Real implementation uses Graph's
create-draft-then-send sequence (plan §9), not the bare ``sendMail`` API,
so a real Graph message id is always available for correlation."""

from abc import ABC, abstractmethod

from app.integrations.graph_email.schemas import EmailSendResult


class EmailClient(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, body: str, order_reference: str) -> EmailSendResult: ...


class GraphNotConfiguredError(Exception):
    """Raised by GraphEmailClient when tenant_id/client_id/client_secret/
    sender_mailbox are not all configured."""
