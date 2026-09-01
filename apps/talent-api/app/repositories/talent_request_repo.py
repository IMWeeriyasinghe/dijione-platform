from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.talent_request import TalentRequest


class TalentRequestRepository:
    """All read/write access to TalentRequest goes through here so tenant
    scoping (``client_id``) is enforced in exactly one place.

    ``client_id=None`` means "staff scope" (TA_MEMBER / CUSTOMER_SUCCESS /
    TA_MANAGER) — no client filter is applied. Any caller holding a
    TALENT_CLIENT persona must always pass their own ``client_id``; callers
    must never accept a client_id from client-supplied request input.
    """

    def __init__(self, db: Session):
        self.db = db

    def _scoped(self, stmt, client_id: int | None, allowed_client_ids: list[int] | None = None):
        if client_id is not None:
            stmt = stmt.where(TalentRequest.client_id == client_id)
        elif allowed_client_ids is not None:
            # Staff portfolio restriction (CLAUDE.md-extension §22) — only
            # applied when the caller has no single-tenant client_id (i.e.
            # is staff); None here (from AuthorizationService) means ALL
            # clients, so no additional filter is added in that case.
            stmt = stmt.where(TalentRequest.client_id.in_(allowed_client_ids))
        return stmt

    def get_by_id(
        self,
        request_id: int,
        *,
        client_id: int | None,
        allowed_client_ids: list[int] | None = None,
    ) -> TalentRequest | None:
        stmt = self._scoped(
            select(TalentRequest).where(TalentRequest.id == request_id),
            client_id,
            allowed_client_ids,
        )
        return self.db.execute(stmt).scalars().first()

    def list_for_scope(
        self,
        *,
        client_id: int | None,
        search: str | None = None,
        stage: str | None = None,
        status: str | None = None,
        filter_client_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ) -> list[TalentRequest]:
        stmt = select(TalentRequest)
        stmt = self._scoped(stmt, client_id, allowed_client_ids)
        if filter_client_id is not None and client_id is None:
            stmt = stmt.where(TalentRequest.client_id == filter_client_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (TalentRequest.designation.ilike(like))
                | (TalentRequest.request_code.ilike(like))
            )
        if stage:
            stmt = stmt.where(TalentRequest.current_stage == stage)
        if status:
            stmt = stmt.where(TalentRequest.lifecycle_status == status)
        stmt = stmt.order_by(TalentRequest.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_by_posting_external_id(
        self, posting_external_id: str, *, provider: str = "LEVER"
    ) -> TalentRequest | None:
        """Lookup for the VerifiedPostingPromotionReconciler's get-or-create
        — mirrors PostingClientMappingRepository.get_for_posting's key."""
        stmt = select(TalentRequest).where(
            TalentRequest.provider == provider,
            TalentRequest.posting_external_id == posting_external_id,
        )
        return self.db.execute(stmt).scalars().first()

    def next_request_code(self) -> str:
        count = self.db.execute(select(func.count()).select_from(TalentRequest)).scalar_one()
        return f"TA-{count + 1:04d}"

    def add(self, talent_request: TalentRequest) -> TalentRequest:
        self.db.add(talent_request)
        self.db.flush()
        return talent_request
