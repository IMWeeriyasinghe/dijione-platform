from pydantic import BaseModel


class EmailSendResult(BaseModel):
    """``message_id`` is the Graph draft/message id captured at
    draft-creation time — a secondary technical correlation aid.
    ``order.order_reference`` in the subject/body remains the primary
    business correlation key (plan §9)."""

    message_id: str
    sent: bool
