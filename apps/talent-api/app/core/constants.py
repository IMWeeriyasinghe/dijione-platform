"""Central enumerations owned by DijiTalentFlow and its integrations.

Platform-level concepts (PlatformRole, the module registry keys for other
modules) live in platform-api now — talent-api only needs its own module
key and business-domain enums. See docs/platform/service-architecture.md.
"""

from enum import StrEnum


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


class CanonicalStage(StrEnum):
    """Client-facing canonical recruitment stages.

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


class PostingClientMappingStatus(StrEnum):
    """Trust state of a Posting -> Client relationship.

    UNMAPPED is the default for every newly-ingested Posting and must fail
    closed: a client-scoped caller may never see a Posting (or anything
    under it) unless its mapping is VERIFIED for their own client_id.
    """

    UNMAPPED = "UNMAPPED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class PostingClientMappingSource(StrEnum):
    """Provenance of a verified Posting -> Client mapping.

    Only MANUAL is settable by anything built so far. The others are seeded
    now so a future HubSpot-backed or Lever-structured-field resolver is an
    additive change, not a schema migration.
    """

    MANUAL = "MANUAL"
    LEVER_STRUCTURED_FIELD = "LEVER_STRUCTURED_FIELD"
    LEVER_DTC_TAG = "LEVER_DTC_TAG"  # governed "DTC - <Client Name>" posting tag
    HUBSPOT = "HUBSPOT"
    OTHER_VERIFIED_SOURCE = "OTHER_VERIFIED_SOURCE"


class DtcResolutionStatus(StrEnum):
    """Internal diagnostic reason for a posting's current client-mapping
    state after DTC-tag reconciliation. Anything other than RESOLVED means
    the posting is NOT client-visible (fail closed)."""

    NO_DTC_TAG = "NO_DTC_TAG"
    RESOLVED = "RESOLVED"
    UNKNOWN_CLIENT_IDENTIFIER = "UNKNOWN_CLIENT_IDENTIFIER"
    AMBIGUOUS_MULTIPLE_TAGS = "AMBIGUOUS_MULTIPLE_TAGS"
    AMBIGUOUS_CLIENT_NAME = "AMBIGUOUS_CLIENT_NAME"
    MALFORMED_TAG = "MALFORMED_TAG"
    CONFLICT_MANUAL_OVERRIDE = "CONFLICT_MANUAL_OVERRIDE"
