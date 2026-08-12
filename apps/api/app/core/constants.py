"""Central enumerations shared across models, schemas and services.

Roles and canonical stages are defined here once so the platform, the
DijiTalentFlow module and the frontend contract (via the API schemas) stay
in sync. See CLAUDE.md sections 10, 11, 30.
"""

from enum import StrEnum


class PlatformRole(StrEnum):
    PLATFORM_USER = "PLATFORM_USER"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class TalentFlowRole(StrEnum):
    TALENT_CLIENT = "TALENT_CLIENT"
    TA_MEMBER = "TA_MEMBER"
    CUSTOMER_SUCCESS = "CUSTOMER_SUCCESS"
    TA_MANAGER = "TA_MANAGER"


# Roles that grant cross-client ("staff") visibility inside DijiTalentFlow.
STAFF_ROLES = {
    TalentFlowRole.TA_MEMBER,
    TalentFlowRole.CUSTOMER_SUCCESS,
    TalentFlowRole.TA_MANAGER,
}

MODULE_TALENT_FLOW = "talent-flow"
MODULE_BIRTHDAY = "birthday"
MODULE_SPARK = "spark"


class CanonicalStage(StrEnum):
    """Client-facing canonical recruitment stages (CLAUDE.md §30).

    External provider (Lever) stage names are mapped into this fixed set by
    the integration mapping layer — never shown directly to clients.
    """

    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    REQUIREMENT_CONFIRMED = "REQUIREMENT_CONFIRMED"
    SOURCING = "SOURCING"
    SCREENING = "SCREENING"
    CLIENT_REVIEW = "CLIENT_REVIEW"
    INTERVIEWS = "INTERVIEWS"
    OFFER = "OFFER"
    ONBOARDING = "ONBOARDING"
    DEPLOYED = "DEPLOYED"


CANONICAL_STAGE_ORDER: list[CanonicalStage] = [
    CanonicalStage.REQUEST_SUBMITTED,
    CanonicalStage.REQUIREMENT_CONFIRMED,
    CanonicalStage.SOURCING,
    CanonicalStage.SCREENING,
    CanonicalStage.CLIENT_REVIEW,
    CanonicalStage.INTERVIEWS,
    CanonicalStage.OFFER,
    CanonicalStage.ONBOARDING,
    CanonicalStage.DEPLOYED,
]


class CustomerSuccessStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class TaStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    VALIDATING = "VALIDATING"
    ATS_LINKED = "ATS_LINKED"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"


class TalentRequestLifecycleStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ApplicationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SHORTLISTED = "SHORTLISTED"
    CLIENT_REVIEW = "CLIENT_REVIEW"
    OFFER = "OFFER"
    HIRED = "HIRED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class CandidateAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    IN_PROCESS = "IN_PROCESS"
    PLACED = "PLACED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class InterviewType(StrEnum):
    INTERNAL_SCREEN = "INTERNAL_SCREEN"
    CLIENT_INTERVIEW = "CLIENT_INTERVIEW"
    TECHNICAL = "TECHNICAL"
    FINAL = "FINAL"


class InterviewStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    NO_SHOW = "NO_SHOW"


class EngagementType(StrEnum):
    FULL_TIME = "FULL_TIME"
    CONTRACT = "CONTRACT"
    PART_TIME = "PART_TIME"
    STAFF_AUGMENTATION = "STAFF_AUGMENTATION"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class DocumentCategory(StrEnum):
    CV = "CV"
    CONTRACT = "CONTRACT"
    REQUIREMENT = "REQUIREMENT"
    OFFER_LETTER = "OFFER_LETTER"
    OTHER = "OTHER"


class NotificationType(StrEnum):
    REQUEST_PENDING_REVIEW = "REQUEST_PENDING_REVIEW"
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    REQUEST_CLARIFICATION_REQUIRED = "REQUEST_CLARIFICATION_REQUIRED"
    CLIENT_FEEDBACK_REQUIRED = "CLIENT_FEEDBACK_REQUIRED"
    INTERVIEW_UPCOMING = "INTERVIEW_UPCOMING"
    APPLICATION_STAGE_CHANGED = "APPLICATION_STAGE_CHANGED"
    INTEGRATION_SYNC_FAILED = "INTEGRATION_SYNC_FAILED"
    NEW_MESSAGE = "NEW_MESSAGE"


class IntegrationProvider(StrEnum):
    LEVER = "LEVER"
    HUBSPOT = "HUBSPOT"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    ERROR = "ERROR"


class ProcessingStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED_DUPLICATE = "IGNORED_DUPLICATE"
    FAILED = "FAILED"
