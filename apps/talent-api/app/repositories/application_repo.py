from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.application import Application
from app.models.talent_request import TalentRequest


class ApplicationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        application_id: int,
        *,
        client_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ) -> Application | None:
        stmt = (
            select(Application)
            .options(joinedload(Application.candidate), joinedload(Application.talent_request))
            .where(Application.id == application_id)
        )
        if client_id is not None:
            stmt = stmt.join(TalentRequest).where(TalentRequest.client_id == client_id)
        elif allowed_client_ids is not None:
            stmt = stmt.join(TalentRequest).where(TalentRequest.client_id.in_(allowed_client_ids))
        return self.db.execute(stmt).scalars().first()

    def list_for_request(
        self, request_id: int, *, client_visible_only: bool = False
    ) -> list[Application]:
        stmt = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(Application.talent_request_id == request_id)
        )
        if client_visible_only:
            stmt = stmt.where(Application.is_client_visible.is_(True))
        return list(self.db.execute(stmt).scalars().all())

    def list_for_candidate(
        self, candidate_id: int, *, allowed_client_ids: list[int] | None = None
    ) -> list[Application]:
        """``allowed_client_ids`` restricts the result to applications whose
        request belongs to a portfolio-scoped staff member's assigned
        clients. ``None`` (unrestricted staff — the Candidate Ownership Rule,
        CLAUDE.md §19) returns every application across every client."""
        stmt = (
            select(Application)
            .options(joinedload(Application.talent_request).joinedload(TalentRequest.client))
            .where(Application.candidate_id == candidate_id)
        )
        if allowed_client_ids is not None:
            stmt = stmt.join(TalentRequest).where(TalentRequest.client_id.in_(allowed_client_ids))
        return list(self.db.execute(stmt).scalars().all())

    def list_for_scope(
        self,
        *,
        client_id: int | None,
        search: str | None = None,
        talent_request_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ) -> list[Application]:
        stmt = (
            select(Application)
            .options(
                joinedload(Application.candidate),
                joinedload(Application.talent_request).joinedload(TalentRequest.client),
            )
            .join(TalentRequest)
        )
        if talent_request_id is not None:
            stmt = stmt.where(Application.talent_request_id == talent_request_id)
        if client_id is not None:
            stmt = stmt.where(TalentRequest.client_id == client_id)
        elif allowed_client_ids is not None:
            stmt = stmt.where(TalentRequest.client_id.in_(allowed_client_ids))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(TalentRequest.designation.ilike(like))
        stmt = stmt.order_by(Application.updated_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def exists_for_pair(self, candidate_id: int, talent_request_id: int) -> bool:
        stmt = select(Application.id).where(
            Application.candidate_id == candidate_id,
            Application.talent_request_id == talent_request_id,
        )
        return self.db.execute(stmt).scalars().first() is not None

    def add(self, application: Application) -> Application:
        self.db.add(application)
        self.db.flush()
        return application
