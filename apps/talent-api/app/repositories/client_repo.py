from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import TalentRequestLifecycleStatus
from app.models.client import Client
from app.models.talent_request import TalentRequest


class ClientRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, client_id: int) -> Client | None:
        return self.db.get(Client, client_id)

    def list_all(self) -> list[Client]:
        return list(self.db.execute(select(Client).order_by(Client.name)).scalars().all())

    def list_for_scope(self, *, allowed_client_ids: list[int] | None = None) -> list[Client]:
        """Portfolio-restricted client listing (CLAUDE.md-extension §22).
        ``allowed_client_ids=None`` means unrestricted (ALL_CLIENTS)."""
        stmt = select(Client).order_by(Client.name)
        if allowed_client_ids is not None:
            stmt = stmt.where(Client.id.in_(allowed_client_ids))
        return list(self.db.execute(stmt).scalars().all())

    def portfolio_counts(self, client_id: int) -> tuple[int, int]:
        total = self.db.execute(
            select(func.count()).select_from(TalentRequest).where(
                TalentRequest.client_id == client_id
            )
        ).scalar_one()
        active = self.db.execute(
            select(func.count())
            .select_from(TalentRequest)
            .where(
                TalentRequest.client_id == client_id,
                TalentRequest.lifecycle_status.in_(
                    [
                        TalentRequestLifecycleStatus.APPROVED.value,
                        TalentRequestLifecycleStatus.IN_PROGRESS.value,
                        TalentRequestLifecycleStatus.PENDING_REVIEW.value,
                    ]
                ),
            )
        ).scalar_one()
        return total, active
