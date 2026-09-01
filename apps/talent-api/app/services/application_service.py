from sqlalchemy.orm import Session

from app.core.constants import (
    MODULE_TALENT_FLOW,
    ApplicationStatus,
    CanonicalStage,
    NotificationType,
    TalentFlowRole,
)
from app.models.application import Application
from app.repositories.application_repo import ApplicationRepository
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.application import ApplicationCreate, ApplicationOut
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


class DuplicateApplicationError(Exception):
    pass


class ApplicationNotFoundError(Exception):
    pass


class InvalidApplicationValueError(Exception):
    """A client-supplied stage/status value is not a recognised enum member."""

    pass


_VALID_STAGES = {s.value for s in CanonicalStage}
_VALID_STATUSES = {s.value for s in ApplicationStatus}


class ApplicationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ApplicationRepository(db)
        self.candidate_repo = CandidateRepository(db)
        self.request_repo = TalentRequestRepository(db)
        self.audit = AuditService()
        self.notifications = NotificationService()

    def create_application(self, *, actor_id: int, payload: ApplicationCreate) -> Application:
        if self.repo.exists_for_pair(payload.candidate_id, payload.talent_request_id):
            raise DuplicateApplicationError(
                f"Candidate {payload.candidate_id} already has an application for "
                f"request {payload.talent_request_id}"
            )
        application = Application(
            candidate_id=payload.candidate_id,
            talent_request_id=payload.talent_request_id,
            current_stage=payload.current_stage,
        )
        self.repo.add(application)
        self.audit.log(
            actor_id=actor_id,
            action="application.created",
            entity_type="Application",
            entity_id=application.id,
            new_state={
                "candidate_id": payload.candidate_id,
                "talent_request_id": payload.talent_request_id,
            },
        )
        return application

    def update_stage(
        self,
        *,
        application_id: int,
        actor_id: int,
        stage: str,
        allowed_client_ids: list[int] | None = None,
    ) -> Application:
        if stage not in _VALID_STAGES:
            raise InvalidApplicationValueError(f"Unknown stage '{stage}'")
        application = self._get_or_raise(application_id, allowed_client_ids=allowed_client_ids)
        previous = application.current_stage
        application.current_stage = stage
        self.audit.log(
            actor_id=actor_id,
            action="application.stage_changed",
            entity_type="Application",
            entity_id=application.id,
            previous_state={"current_stage": previous},
            new_state={"current_stage": stage},
        )
        if application.is_client_visible:
            self._notify_client(application, NotificationType.APPLICATION_STAGE_CHANGED.value,
                                 f"Update on {application.candidate.full_name}",
                                 f"Now at stage: {stage.replace('_', ' ').title()}")
        return application

    def update_status(
        self,
        *,
        application_id: int,
        actor_id: int,
        status: str,
        rejection_reason: str,
        allowed_client_ids: list[int] | None = None,
    ) -> Application:
        if status not in _VALID_STATUSES:
            raise InvalidApplicationValueError(f"Unknown status '{status}'")
        application = self._get_or_raise(application_id, allowed_client_ids=allowed_client_ids)
        previous = application.status
        application.status = status
        application.rejection_reason = rejection_reason
        self.audit.log(
            actor_id=actor_id,
            action="application.status_changed",
            entity_type="Application",
            entity_id=application.id,
            previous_state={"status": previous},
            new_state={"status": status},
        )
        return application

    def update_score(
        self,
        *,
        application_id: int,
        actor_id: int,
        score: float,
        recruiter_notes: str,
        allowed_client_ids: list[int] | None = None,
    ) -> Application:
        application = self._get_or_raise(application_id, allowed_client_ids=allowed_client_ids)
        application.score = score
        if recruiter_notes:
            application.recruiter_notes = recruiter_notes
        self.audit.log(
            actor_id=actor_id,
            action="application.scored",
            entity_type="Application",
            entity_id=application.id,
            new_state={"score": score},
        )
        return application

    def update_visibility(
        self,
        *,
        application_id: int,
        actor_id: int,
        is_client_visible: bool,
        client_visible_notes: str,
        allowed_client_ids: list[int] | None = None,
    ) -> Application:
        application = self._get_or_raise(application_id, allowed_client_ids=allowed_client_ids)
        application.is_client_visible = is_client_visible
        if client_visible_notes:
            application.client_visible_notes = client_visible_notes
        self.audit.log(
            actor_id=actor_id,
            action="application.visibility_changed",
            entity_type="Application",
            entity_id=application.id,
            new_state={"is_client_visible": is_client_visible},
        )
        if is_client_visible:
            self._notify_client(
                application,
                NotificationType.CLIENT_FEEDBACK_REQUIRED.value,
                f"Candidate ready for review: {application.candidate.full_name}",
                client_visible_notes,
            )
        return application

    def _notify_client(self, application: Application, type_: str, title: str, body: str) -> None:
        self.notifications.notify_module_role(
            module_key=MODULE_TALENT_FLOW,
            role=TalentFlowRole.TALENT_CLIENT.value,
            client_id=application.talent_request.client_id,
            type=type_,
            title=title,
            body=body,
            related_entity_type="Application",
            related_entity_id=application.id,
        )

    def _get_or_raise(
        self, application_id: int, *, allowed_client_ids: list[int] | None = None
    ) -> Application:
        # allowed_client_ids restricts a portfolio-scoped staff user to their
        # assigned clients; an out-of-portfolio id resolves to None -> 404
        # (existence is not leaked), identical to the read-path behaviour.
        application = self.repo.get_by_id(application_id, allowed_client_ids=allowed_client_ids)
        if application is None:
            raise ApplicationNotFoundError(application_id)
        return application

    def to_out(self, application: Application) -> ApplicationOut:
        return ApplicationOut(
            id=application.id,
            candidate_id=application.candidate_id,
            candidate_name=application.candidate.full_name if application.candidate else "",
            talent_request_id=application.talent_request_id,
            client_name=(
                application.talent_request.client.name
                if application.talent_request and application.talent_request.client
                else ""
            ),
            designation=application.talent_request.designation if application.talent_request else "",
            current_stage=application.current_stage,
            status=application.status,
            score=application.score,
            recruiter_notes=application.recruiter_notes,
            client_visible_notes=application.client_visible_notes,
            rejection_reason=application.rejection_reason,
            is_client_visible=application.is_client_visible,
            created_at=application.created_at,
            updated_at=application.updated_at,
        )
