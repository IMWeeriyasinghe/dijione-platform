from sqlalchemy.orm import Session

from app.core.constants import (
    MODULE_TALENT_FLOW,
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


class TalentRequestNotFoundError(Exception):
    pass


class InvalidApplicationValueError(Exception):
    """A client-supplied stage/status value is not a recognised enum member."""

    pass


class ApplicationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ApplicationRepository(db)
        self.candidate_repo = CandidateRepository(db)
        self.request_repo = TalentRequestRepository(db)
        self.audit = AuditService()
        self.notifications = NotificationService()

    def create_application(
        self,
        *,
        actor_id: int,
        payload: ApplicationCreate,
        allowed_client_ids: list[int] | None = None,
    ) -> Application:
        # A portfolio-restricted staff user must not be able to link a
        # candidate to a talent_request_id outside their portfolio just by
        # supplying its id in the request body (unlike the other Application
        # mutation endpoints, this one is not nested under
        # /requests/{request_id}/..., so there is no URL-path id for the
        # route layer to pre-scope — the check has to happen here).
        request = self.request_repo.get_by_id(
            payload.talent_request_id, client_id=None, allowed_client_ids=allowed_client_ids
        )
        if request is None:
            raise TalentRequestNotFoundError(payload.talent_request_id)
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

    # NOTE: `update_stage` / `update_status` / `update_score` were removed
    # (DijiTalentFlow monitoring-first iteration). Recruitment stage and
    # status are Lever facts, refreshed from the Recruitment Source by
    # `VerifiedPostingPromotionReconciler` on every reconcile; `score` has
    # no authoritative source. The corresponding PATCH routes now 403. The
    # `Application.score` column is retained purely for zero-risk
    # back-compat and is recorded as tech debt in
    # `docs/talent-flow/data-model.md` — nothing reads or writes it.

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
