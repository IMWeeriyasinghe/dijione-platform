from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.application import Application
from app.models.interview import Interview
from app.models.talent_request import TalentRequest


class InterviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, interview_id: int) -> Interview | None:
        return self.db.get(Interview, interview_id)

    def list_for_application(self, application_id: int) -> list[Interview]:
        stmt = select(Interview).where(Interview.application_id == application_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_for_scope(
        self, *, client_id: int | None, allowed_client_ids: list[int] | None = None
    ) -> list[Interview]:
        stmt = (
            select(Interview)
            .join(Application, Interview.application_id == Application.id)
            .join(TalentRequest, Application.talent_request_id == TalentRequest.id)
            .options(
                joinedload(Interview.application).joinedload(Application.candidate),
                joinedload(Interview.application)
                .joinedload(Application.talent_request)
                .joinedload(TalentRequest.client),
            )
        )
        if client_id is not None:
            stmt = stmt.where(TalentRequest.client_id == client_id, Interview.client_visible.is_(True))
        elif allowed_client_ids is not None:
            stmt = stmt.where(TalentRequest.client_id.in_(allowed_client_ids))
        stmt = stmt.order_by(Interview.scheduled_at)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, interview: Interview) -> Interview:
        self.db.add(interview)
        self.db.flush()
        return interview
