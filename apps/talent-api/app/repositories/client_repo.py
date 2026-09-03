from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import TalentRequestLifecycleStatus
from app.models.application import Application
from app.models.client import Client
from app.models.talent_request import TalentRequest
from app.services.talent_request_service import ACTIVE_APPLICATION_STATUSES


@dataclass
class PortfolioSummary:
    total_requests: int
    active_requests: int
    active_application_count: int
    client_visible_count: int
    latest_request_at: datetime | None


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

    def portfolio_summary(self, client_id: int) -> PortfolioSummary:
        """Richer Client Portfolios card metrics (plan §E): the existing
        total/active request counts, plus how much of this client's
        pipeline is actually moving (active applications), how much has
        actually been shown to them (client-visible applications — the one
        real curation signal), and when they were last engaged."""
        total, active = self.portfolio_counts(client_id)

        active_application_count = self.db.execute(
            select(func.count(Application.id))
            .select_from(Application)
            .join(TalentRequest, Application.talent_request_id == TalentRequest.id)
            .where(
                TalentRequest.client_id == client_id,
                Application.status.in_(list(ACTIVE_APPLICATION_STATUSES)),
            )
        ).scalar_one()

        client_visible_count = self.db.execute(
            select(func.count(Application.id))
            .select_from(Application)
            .join(TalentRequest, Application.talent_request_id == TalentRequest.id)
            .where(
                TalentRequest.client_id == client_id,
                Application.is_client_visible.is_(True),
            )
        ).scalar_one()

        latest_request_at = self.db.execute(
            select(func.max(TalentRequest.created_at)).where(TalentRequest.client_id == client_id)
        ).scalar_one()

        return PortfolioSummary(
            total_requests=total,
            active_requests=active,
            active_application_count=active_application_count,
            client_visible_count=client_visible_count,
            latest_request_at=latest_request_at,
        )
