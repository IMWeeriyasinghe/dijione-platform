from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.access_group import GroupModuleRole, UserGroupMembership
from app.models.notification import Notification
from app.models.user import User, UserModuleRole
from app.repositories.notification_repo import NotificationRepository
from app.services.authorization_service import AuthorizationService


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

    def create_once(self, *, user_ids: set[int], dedupe_key: str, **fields) -> int:
        """At most one notification per recipient and key, also under concurrency."""
        created = 0
        for user_id in sorted(user_ids):
            try:
                with self.db.begin_nested():
                    self.db.add(Notification(user_id=user_id, dedupe_key=dedupe_key, **fields))
                    self.db.flush()
                created += 1
            except IntegrityError:
                continue
        return created

    def active_users(self, user_ids: set[int]) -> set[int]:
        stmt = select(User.id).where(User.id.in_(user_ids), User.is_active.is_(True))
        return set(self.db.execute(stmt).scalars().all())

    def holders_of(self, module_key: str, permissions: set[str]) -> set[int]:
        """Active users whose effective permissions (direct and group) include all of these."""
        direct = select(UserModuleRole.user_id).where(UserModuleRole.module_key == module_key, UserModuleRole.enabled.is_(True))
        grouped = (
            select(UserGroupMembership.user_id)
            .join(GroupModuleRole, GroupModuleRole.access_group_id == UserGroupMembership.access_group_id)
            .where(GroupModuleRole.module_key == module_key, GroupModuleRole.enabled.is_(True))
        )
        candidates = set(self.db.execute(direct).scalars().all()) | set(self.db.execute(grouped).scalars().all())
        users = self.db.execute(select(User).where(User.id.in_(candidates), User.is_active.is_(True))).scalars().all()
        authz = AuthorizationService(self.db)
        return {u.id for u in users if permissions <= authz.effective_permissions(u, module_key)}

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
        client_id: int | None = None,
    ) -> list[Notification]:
        """Notify every user holding ``role`` in ``module_key``, optionally
        narrowed to a single ``client_id`` (e.g. "every TALENT_CLIENT user at
        this specific client" rather than every client org) — talent-api
        uses this instead of resolving ``UserModuleRole`` rows itself, since
        that table is platform-owned."""
        stmt = select(UserModuleRole.user_id).where(
            UserModuleRole.module_key == module_key, UserModuleRole.role == role
        )
        if client_id is not None:
            stmt = stmt.where(UserModuleRole.client_id == client_id)
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
