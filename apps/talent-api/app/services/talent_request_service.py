from sqlalchemy.orm import Session

from app.core.constants import (
    CANONICAL_STAGE_ORDER,
    MODULE_TALENT_FLOW,
    ApplicationStatus,
    CanonicalStage,
    CustomerSuccessStatus,
    NotificationType,
    TalentFlowRole,
    TalentRequestLifecycleStatus,
    TaStatus,
)
from app.models.talent_request import TalentRequest
from app.repositories.application_repo import ApplicationRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.talent_request import (
    StageProgressOut,
    TalentRequestCreate,
    TalentRequestOut,
)
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

ACTIVE_APPLICATION_STATUSES = {
    ApplicationStatus.ACTIVE.value,
    ApplicationStatus.SHORTLISTED.value,
    ApplicationStatus.CLIENT_REVIEW.value,
    ApplicationStatus.OFFER.value,
}

_STAGE_STATUS_TEXT = {
    CanonicalStage.REQUEST_SUBMITTED: "Request submitted — awaiting review",
    CanonicalStage.REQUIREMENT_CONFIRMED: "Requirement confirmed — preparing to source",
    CanonicalStage.SOURCING: "Sourcing candidates",
    CanonicalStage.SCREENING: "Screening candidates",
    CanonicalStage.CLIENT_REVIEW: "Candidates ready for your review",
    CanonicalStage.INTERVIEWS: "Client interviews in progress",
    CanonicalStage.OFFER: "Offer in progress",
    CanonicalStage.ONBOARDING: "Onboarding in progress",
    CanonicalStage.DEPLOYED: "Candidate deployed",
}


class TalentRequestNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class TalentRequestService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TalentRequestRepository(db)
        self.application_repo = ApplicationRepository(db)
        self.audit = AuditService()
        self.notifications = NotificationService()

    def create_request(
        self, *, client_id: int, created_by: int, payload: TalentRequestCreate
    ) -> TalentRequest:
        request = TalentRequest(
            request_code=self.repo.next_request_code(),
            client_id=client_id,
            designation=payload.designation,
            description=payload.description,
            required_skills=",".join(payload.required_skills),
            seniority=payload.seniority,
            location=payload.location,
            engagement_type=payload.engagement_type,
            target_start_date=payload.target_start_date,
            notes=payload.notes,
            current_stage=CanonicalStage.REQUEST_SUBMITTED.value,
            lifecycle_status=TalentRequestLifecycleStatus.PENDING_REVIEW.value,
            customer_success_status=CustomerSuccessStatus.PENDING_REVIEW.value,
            ta_status=TaStatus.NOT_STARTED.value,
            client_safe_status_text=_STAGE_STATUS_TEXT[CanonicalStage.REQUEST_SUBMITTED],
            created_by=created_by,
        )
        self.repo.add(request)

        self.audit.log(
            actor_id=created_by,
            action="talent_request.created",
            entity_type="TalentRequest",
            entity_id=request.id,
            new_state={"designation": request.designation, "client_id": client_id},
        )
        self.notifications.notify_module_role(
            module_key=MODULE_TALENT_FLOW,
            role=TalentFlowRole.CUSTOMER_SUCCESS.value,
            type=NotificationType.REQUEST_PENDING_REVIEW.value,
            title=f"New talent request: {request.designation}",
            body=f"{request.request_code} requires Customer Success review.",
            related_entity_type="TalentRequest",
            related_entity_id=request.id,
        )
        return request

    def review_request(
        self,
        *,
        request_id: int,
        actor_id: int,
        decision: str,
        reason: str,
        allowed_client_ids: list[int] | None = None,
    ) -> TalentRequest:
        request = self.repo.get_by_id(
            request_id, client_id=None, allowed_client_ids=allowed_client_ids
        )
        if request is None:
            raise TalentRequestNotFoundError(request_id)

        previous_status = request.customer_success_status
        if decision == CustomerSuccessStatus.APPROVED.value:
            request.customer_success_status = CustomerSuccessStatus.APPROVED.value
            request.lifecycle_status = TalentRequestLifecycleStatus.APPROVED.value
            request.current_stage = CanonicalStage.REQUIREMENT_CONFIRMED.value
            request.ta_status = TaStatus.VALIDATING.value
            request.client_safe_status_text = _STAGE_STATUS_TEXT[
                CanonicalStage.REQUIREMENT_CONFIRMED
            ]
            notif_type = NotificationType.REQUEST_APPROVED.value
            notif_title = f"Request approved: {request.designation}"
            notify_role = TalentFlowRole.TA_MEMBER.value
        elif decision == CustomerSuccessStatus.REJECTED.value:
            request.customer_success_status = CustomerSuccessStatus.REJECTED.value
            request.lifecycle_status = TalentRequestLifecycleStatus.REJECTED.value
            request.client_safe_status_text = "Request rejected — see notes"
            notif_type = NotificationType.REQUEST_REJECTED.value
            notif_title = f"Request rejected: {request.designation}"
            notify_role = TalentFlowRole.TALENT_CLIENT.value
        elif decision == CustomerSuccessStatus.CLARIFICATION_REQUIRED.value:
            request.customer_success_status = CustomerSuccessStatus.CLARIFICATION_REQUIRED.value
            request.client_safe_status_text = "Clarification requested — please respond"
            notif_type = NotificationType.REQUEST_CLARIFICATION_REQUIRED.value
            notif_title = f"Clarification needed: {request.designation}"
            notify_role = TalentFlowRole.TALENT_CLIENT.value
        else:
            raise InvalidTransitionError(f"Unknown decision: {decision}")

        self.audit.log(
            actor_id=actor_id,
            action="talent_request.reviewed",
            entity_type="TalentRequest",
            entity_id=request.id,
            previous_state={"customer_success_status": previous_status},
            new_state={"customer_success_status": request.customer_success_status, "reason": reason},
        )

        if notify_role == TalentFlowRole.TALENT_CLIENT.value:
            self._notify_client_users(
                request.client_id,
                notif_type,
                notif_title,
                reason or request.client_safe_status_text,
                request.id,
            )
        else:
            self.notifications.notify_module_role(
                module_key=MODULE_TALENT_FLOW,
                role=notify_role,
                type=notif_type,
                title=notif_title,
                body=reason,
                related_entity_type="TalentRequest",
                related_entity_id=request.id,
            )
        return request

    def _notify_client_users(
        self, client_id: int, notif_type: str, title: str, body: str, entity_id: int
    ) -> None:
        self.notifications.notify_module_role(
            module_key=MODULE_TALENT_FLOW,
            role=TalentFlowRole.TALENT_CLIENT.value,
            client_id=client_id,
            type=notif_type,
            title=title,
            body=body,
            related_entity_type="TalentRequest",
            related_entity_id=entity_id,
        )

    def update_stage(
        self,
        *,
        request_id: int,
        actor_id: int,
        stage: str,
        client_safe_status_text: str | None,
        allowed_client_ids: list[int] | None = None,
    ) -> TalentRequest:
        request = self.repo.get_by_id(
            request_id, client_id=None, allowed_client_ids=allowed_client_ids
        )
        if request is None:
            raise TalentRequestNotFoundError(request_id)
        if stage not in [s.value for s in CANONICAL_STAGE_ORDER]:
            raise InvalidTransitionError(f"Unknown stage: {stage}")

        previous_stage = request.current_stage
        request.current_stage = stage
        request.client_safe_status_text = client_safe_status_text or _STAGE_STATUS_TEXT.get(
            CanonicalStage(stage), request.client_safe_status_text
        )
        if stage == CanonicalStage.DEPLOYED.value:
            request.lifecycle_status = TalentRequestLifecycleStatus.FULFILLED.value
            request.ta_status = TaStatus.COMPLETED.value
        elif request.lifecycle_status == TalentRequestLifecycleStatus.APPROVED.value:
            request.lifecycle_status = TalentRequestLifecycleStatus.IN_PROGRESS.value
            request.ta_status = TaStatus.IN_PROGRESS.value

        self.audit.log(
            actor_id=actor_id,
            action="talent_request.stage_changed",
            entity_type="TalentRequest",
            entity_id=request.id,
            previous_state={"current_stage": previous_stage},
            new_state={"current_stage": stage},
        )
        self._notify_client_users(
            request.client_id,
            NotificationType.APPLICATION_STAGE_CHANGED.value,
            f"Update on {request.designation}",
            request.client_safe_status_text,
            request.id,
        )
        return request

    def update_ta_status(
        self,
        *,
        request_id: int,
        actor_id: int,
        ta_status: str,
        allowed_client_ids: list[int] | None = None,
    ) -> TalentRequest:
        request = self.repo.get_by_id(
            request_id, client_id=None, allowed_client_ids=allowed_client_ids
        )
        if request is None:
            raise TalentRequestNotFoundError(request_id)
        previous = request.ta_status
        request.ta_status = ta_status
        self.audit.log(
            actor_id=actor_id,
            action="talent_request.ta_status_changed",
            entity_type="TalentRequest",
            entity_id=request.id,
            previous_state={"ta_status": previous},
            new_state={"ta_status": ta_status},
        )
        return request

    def to_out(self, request: TalentRequest) -> TalentRequestOut:
        stage_values = [s.value for s in CANONICAL_STAGE_ORDER]
        current_idx = stage_values.index(request.current_stage)
        last_idx = len(stage_values) - 1
        progress_percent = round((current_idx / last_idx) * 100) if last_idx else 0

        timeline = []
        for idx, stage in enumerate(CANONICAL_STAGE_ORDER):
            state = "DONE" if idx < current_idx else "CURRENT" if idx == current_idx else "UPCOMING"
            timeline.append(
                StageProgressOut(
                    stage=stage.value,
                    label=stage.value.replace("_", " ").title(),
                    state=state,
                )
            )

        applications = self.application_repo.list_for_request(request.id)
        active_count = sum(1 for a in applications if a.status in ACTIVE_APPLICATION_STATUSES)

        return TalentRequestOut(
            id=request.id,
            request_code=request.request_code,
            client_id=request.client_id,
            client_name=request.client.name if request.client else None,
            designation=request.designation,
            description=request.description,
            required_skills=[s for s in request.required_skills.split(",") if s],
            seniority=request.seniority,
            location=request.location,
            engagement_type=request.engagement_type,
            target_start_date=request.target_start_date,
            notes=request.notes,
            current_stage=request.current_stage,
            lifecycle_status=request.lifecycle_status,
            customer_success_status=request.customer_success_status,
            ta_status=request.ta_status,
            client_safe_status_text=request.client_safe_status_text,
            priority=request.priority,
            progress_percent=progress_percent,
            stage_timeline=timeline,
            active_application_count=active_count,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )
