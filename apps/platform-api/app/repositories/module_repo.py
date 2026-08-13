from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.module import ApplicationModule


class ModuleRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_enabled(self) -> list[ApplicationModule]:
        stmt = (
            select(ApplicationModule)
            .where(ApplicationModule.enabled.is_(True))
            .order_by(ApplicationModule.display_order)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_key(self, key: str) -> ApplicationModule | None:
        stmt = select(ApplicationModule).where(ApplicationModule.key == key)
        return self.db.execute(stmt).scalars().first()
