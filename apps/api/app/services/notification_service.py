from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import UserModuleRole
from app.repositories.notification_repo import NotificationRepository


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = NotificationRepository(db)

    def notify_user(
        self,
        *,
        user_id: int,
        type: str,
        title: str,
        body: str = "",
        related_entity_type: str | None = None,
        related_entity_id: int | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        return self.repo.add(notification)

    def notify_module_role(
        self,
        *,
        module_key: str,
        role: str,
        type: str,
        title: str,
        body: str = "",
        related_entity_type: str | None = None,
        related_entity_id: int | None = None,
    ) -> list[Notification]:
        stmt = select(UserModuleRole.user_id).where(
            UserModuleRole.module_key == module_key, UserModuleRole.role == role
        )
        user_ids = [row[0] for row in self.db.execute(stmt).all()]
        return [
            self.notify_user(
                user_id=uid,
                type=type,
                title=title,
                body=body,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
            )
            for uid in user_ids
        ]
