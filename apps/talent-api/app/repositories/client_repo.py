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

    def get_by_platform_id(self, platform_client_id: str) -> Client | None:
        """Resolve a platform ``Client.public_id`` (carried in a client-scope
        JWT claim) to the local extension row."""
        return self.db.execute(
            select(Client).where(Client.platform_client_id == platform_client_id)
        ).scalars().first()

    def list_by_platform_ids(self, platform_client_ids: list[str]) -> list[Client]:
        if not platform_client_ids:
            return []
        return list(
            self.db.execute(
                select(Client).where(Client.platform_client_id.in_(platform_client_ids))
            ).scalars().all()
        )

    def get_by_name(self, name: str) -> Client | None:
        """Exact, case-preserving match (``Client.name`` is unique). Used by
        governed DTC-tag client resolution — no fuzzy matching."""
        return self.db.execute(
            select(Client).where(Client.name == name)
        ).scalars().first()

    def find_by_name(self, name: str) -> list[Client]:
        """Defensive multi-match check for the reconciler (``name`` is unique
        so this should return 0 or 1; >1 => AMBIGUOUS_CLIENT_NAME, fail closed)."""
        return list(self.db.execute(select(Client).where(Client.name == name)).scalars().all())

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
