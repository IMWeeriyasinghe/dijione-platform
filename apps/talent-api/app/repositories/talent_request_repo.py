from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import PostingClientMappingStatus
from app.models.posting_client_mapping import PostingClientMapping
from app.models.talent_request import TalentRequest


def client_may_access_request():
    """Fail-closed client gate. A request promoted from a posting is visible
    to its client only while a VERIFIED mapping names that same client, so
    unmapping or re-tagging takes effect on the next read. Requests with no
    source posting have no mapping to consult."""
    return or_(
        TalentRequest.posting_external_id.is_(None),
        exists().where(
            PostingClientMapping.provider == TalentRequest.provider,
            PostingClientMapping.posting_external_id == TalentRequest.posting_external_id,
            PostingClientMapping.status == PostingClientMappingStatus.VERIFIED.value,
            PostingClientMapping.client_id == TalentRequest.client_id,
        ),
    )


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
            stmt = stmt.where(TalentRequest.client_id == client_id, client_may_access_request())
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

    def _filtered(
        self,
        stmt,
        *,
        client_id: int | None,
        search: str | None = None,
        stage: str | None = None,
        statuses: list[str] | None = None,
        filter_client_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ):
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
        if statuses:
            stmt = stmt.where(TalentRequest.lifecycle_status.in_(statuses))
        return stmt

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
        stmt = self._filtered(
            select(TalentRequest),
            client_id=client_id,
            search=search,
            stage=stage,
            statuses=[status] if status else None,
            filter_client_id=filter_client_id,
            allowed_client_ids=allowed_client_ids,
        )
        stmt = stmt.order_by(TalentRequest.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def list_page(
        self,
        *,
        client_id: int | None,
        search: str | None = None,
        stage: str | None = None,
        statuses: list[str] | None = None,
        filter_client_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[TalentRequest], int]:
        """One page of requests + the total, with the exact scoping of
        ``list_for_scope`` (client tenant / staff portfolio, never
        caller-widened). Ordered ``created_at DESC, id DESC`` so ties never
        reorder between pages; the client is eager-loaded for the cards."""
        filters = dict(
            client_id=client_id,
            search=search.strip() if search and search.strip() else None,
            stage=stage,
            statuses=statuses,
            filter_client_id=filter_client_id,
            allowed_client_ids=allowed_client_ids,
        )
        total = self.db.execute(
            self._filtered(select(func.count(TalentRequest.id)), **filters)
        ).scalar_one()
        stmt = self._filtered(
            select(TalentRequest).options(joinedload(TalentRequest.client)), **filters
        ).order_by(TalentRequest.created_at.desc(), TalentRequest.id.desc())
        rows = self.db.execute(stmt.limit(limit).offset(offset)).scalars().all()
        return list(rows), int(total)

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

    def list_source_linked(self, *, provider: str = "LEVER") -> list[TalentRequest]:
        return list(
            self.db.execute(
                select(TalentRequest).where(
                    TalentRequest.provider == provider,
                    TalentRequest.posting_external_id.is_not(None),
                )
            ).scalars().all()
        )

    def next_request_code(self) -> str:
        count = self.db.execute(select(func.count()).select_from(TalentRequest)).scalar_one()
        return f"TA-{count + 1:04d}"

    def add(self, talent_request: TalentRequest) -> TalentRequest:
        self.db.add(talent_request)
        self.db.flush()
        return talent_request
