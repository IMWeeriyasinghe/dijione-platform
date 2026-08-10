from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserModuleRole


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_persona_key(self, persona_key: str) -> User | None:
        stmt = select(User).where(User.persona_key == persona_key)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_active_personas(self) -> list[User]:
        stmt = select(User).where(User.persona_key.is_not(None)).order_by(User.id)
        return list(self.db.execute(stmt).scalars().all())

    def module_roles_for(self, user_id: int) -> list[UserModuleRole]:
        stmt = select(UserModuleRole).where(UserModuleRole.user_id == user_id)
        return list(self.db.execute(stmt).scalars().all())

    def module_role_for(self, user_id: int, module_key: str) -> UserModuleRole | None:
        stmt = select(UserModuleRole).where(
            UserModuleRole.user_id == user_id, UserModuleRole.module_key == module_key
        )
        return self.db.execute(stmt).scalars().first()
