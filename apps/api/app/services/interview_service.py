from sqlalchemy.orm import Session

from app.core.constants import NotificationType
from app.models.interview import Interview
from app.repositories.application_repo import ApplicationRepository
from app.repositories.interview_repo import InterviewRepository
from app.schemas.interview import ClientInterviewOut, InterviewCreate, InterviewOut
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


class ApplicationNotFoundError(Exception):
    pass


class InterviewNotFoundError(Exception):
    pass


class InterviewService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = InterviewRepository(db)
        self.application_repo = ApplicationRepository(db)
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    def create_interview(self, *, actor_id: int, payload: InterviewCreate) -> Interview:
        application = self.application_repo.get_by_id(payload.application_id)
        if application is None:
            raise ApplicationNotFoundError(payload.application_id)
        interview = Interview(
            application_id=payload.application_id,
            scheduled_at=payload.scheduled_at,
            interview_type=payload.interview_type,
            meeting_link=payload.meeting_link,
            client_visible=payload.client_visible,
            notes=payload.notes,
        )
        self.repo.add(interview)
        self.audit.log(
            actor_id=actor_id,
            action="interview.scheduled",
            entity_type="Interview",
            entity_id=interview.id,
            new_state={"application_id": payload.application_id, "scheduled_at": str(payload.scheduled_at)},
        )
        if payload.client_visible:
            self._notify_client(application, interview)
        return interview

    def update_status(self, *, interview_id: int, actor_id: int, status: str, notes: str) -> Interview:
        interview = self.repo.get_by_id(interview_id)
        if interview is None:
            raise InterviewNotFoundError(interview_id)
        previous = interview.status
        interview.status = status
        if notes:
            interview.notes = notes
        self.audit.log(
            actor_id=actor_id,
            action="interview.status_changed",
            entity_type="Interview",
            entity_id=interview.id,
            previous_state={"status": previous},
            new_state={"status": status},
        )
        return interview

    def _notify_client(self, application, interview: Interview) -> None:
        from sqlalchemy import select

        from app.core.constants import MODULE_TALENT_FLOW, TalentFlowRole
        from app.models.user import UserModuleRole

        client_id = application.talent_request.client_id
        stmt = select(UserModuleRole.user_id).where(
            UserModuleRole.module_key == MODULE_TALENT_FLOW,
            UserModuleRole.role == TalentFlowRole.TALENT_CLIENT.value,
            UserModuleRole.client_id == client_id,
        )
        for (user_id,) in self.db.execute(stmt).all():
            self.notifications.notify_user(
                user_id=user_id,
                type=NotificationType.INTERVIEW_UPCOMING.value,
                title=f"Interview scheduled: {application.candidate.full_name}",
                body=f"{interview.scheduled_at.strftime('%b %d, %Y at %I:%M %p UTC')}",
                related_entity_type="Interview",
                related_entity_id=interview.id,
            )

    def to_out(self, interview: Interview) -> InterviewOut:
        application = interview.application
        return InterviewOut(
            id=interview.id,
            application_id=interview.application_id,
            talent_request_id=application.talent_request_id if application else 0,
            candidate_name=application.candidate.full_name if application and application.candidate else "",
            client_name=(
                application.talent_request.client.name
                if application and application.talent_request and application.talent_request.client
                else ""
            ),
            designation=application.talent_request.designation
            if application and application.talent_request
            else "",
            scheduled_at=interview.scheduled_at,
            interview_type=interview.interview_type,
            status=interview.status,
            meeting_link=interview.meeting_link,
            client_visible=interview.client_visible,
            notes=interview.notes,
        )

    def to_client_out(self, interview: Interview) -> ClientInterviewOut:
        application = interview.application
        return ClientInterviewOut(
            id=interview.id,
            talent_request_id=application.talent_request_id if application else 0,
            candidate_name=application.candidate.full_name if application and application.candidate else "",
            designation=application.talent_request.designation
            if application and application.talent_request
            else "",
            scheduled_at=interview.scheduled_at,
            interview_type=interview.interview_type,
            status=interview.status,
            meeting_link=interview.meeting_link or None,
        )
