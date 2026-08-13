from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_request(self, request_id: int) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.talent_request_id == request_id)
            .order_by(Message.created_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    def add(self, message: Message) -> Message:
        self.db.add(message)
        self.db.flush()
        return message
