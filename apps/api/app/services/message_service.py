from sqlalchemy.orm import Session

from app.core.constants import MODULE_TALENT_FLOW, STAFF_ROLES, NotificationType, TalentFlowRole
from app.models.message import Message
from app.repositories.message_repo import MessageRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.message import MessageOut
from app.services.notification_service import NotificationService


class TalentRequestNotFoundError(Exception):
    pass


class MessageService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = MessageRepository(db)
        self.request_repo = TalentRequestRepository(db)
        self.notifications = NotificationService(db)

    def send_message(
        self, *, talent_request_id: int, sender_id: int, sender_role: str, body: str
    ) -> Message:
        request = self.request_repo.get_by_id(talent_request_id, client_id=None)
        if request is None:
            raise TalentRequestNotFoundError(talent_request_id)
        message = Message(
            talent_request_id=talent_request_id,
            sender_id=sender_id,
            sender_role=sender_role,
            body=body,
        )
        self.repo.add(message)

        if sender_role == TalentFlowRole.TALENT_CLIENT.value:
            self.notifications.notify_module_role(
                module_key=MODULE_TALENT_FLOW,
                role=TalentFlowRole.TA_MEMBER.value,
                type=NotificationType.NEW_MESSAGE.value,
                title=f"New message on {request.request_code}",
                body=body[:200],
                related_entity_type="TalentRequest",
                related_entity_id=request.id,
            )
        elif sender_role in {r.value for r in STAFF_ROLES}:
            from sqlalchemy import select

            from app.models.user import UserModuleRole

            stmt = select(UserModuleRole.user_id).where(
                UserModuleRole.module_key == MODULE_TALENT_FLOW,
                UserModuleRole.role == TalentFlowRole.TALENT_CLIENT.value,
                UserModuleRole.client_id == request.client_id,
            )
            for (user_id,) in self.db.execute(stmt).all():
                self.notifications.notify_user(
                    user_id=user_id,
                    type=NotificationType.NEW_MESSAGE.value,
                    title=f"New message on {request.request_code}",
                    body=body[:200],
                    related_entity_type="TalentRequest",
                    related_entity_id=request.id,
                )
        return message

    def list_for_request(self, talent_request_id: int) -> list[Message]:
        return self.repo.list_for_request(talent_request_id)

    def to_out(self, message: Message, sender_name: str) -> MessageOut:
        return MessageOut(
            id=message.id,
            talent_request_id=message.talent_request_id,
            sender_id=message.sender_id,
            sender_name=sender_name,
            sender_role=message.sender_role,
            body=message.body,
            created_at=message.created_at,
        )
