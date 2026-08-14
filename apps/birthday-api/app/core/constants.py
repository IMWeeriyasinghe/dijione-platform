"""Central enumerations owned by DijiBirthday.

Platform-level concepts (PlatformRole, the module registry keys for other
modules) live in platform-api now — birthday-api only needs its own module
key and business-domain enums. See docs/platform/service-architecture.md.
"""

from enum import StrEnum

MODULE_BIRTHDAY = "birthday"


class BirthdayRole(StrEnum):
    BIRTHDAY_USER = "BIRTHDAY_USER"
    BIRTHDAY_ADMIN = "BIRTHDAY_ADMIN"
    BIRTHDAY_SUPPLIER = "BIRTHDAY_SUPPLIER"


class LeadTimeClass(StrEnum):
    NORMAL = "NORMAL"
    SHORT_NOTICE = "SHORT_NOTICE"
    URGENT = "URGENT"


class OrderStatus(StrEnum):
    # Pre-fulfilment / approval-workflow states (Phase-Next §2). Orders are
    # created DRAFT; the readiness check auto-promotes to
    # READY_FOR_APPROVAL once eligible+address-verified+supplier-assigned;
    # APPROVED is a human decision (never automatic) and is the only status
    # from which an order may be sent to a supplier.
    DRAFT = "DRAFT"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"
    PLANNED = "PLANNED"  # legacy pre-approval-workflow status, kept for backward compatibility
    ON_HOLD = "ON_HOLD"
    SENT_TO_SUPPLIER = "SENT_TO_SUPPLIER"
    SUPPLIER_REVIEW = "SUPPLIER_REVIEW"
    CHANGE_REQUESTED = "CHANGE_REQUESTED"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    UNABLE_TO_FULFIL = "UNABLE_TO_FULFIL"
    CANCELLED = "CANCELLED"
    REQUIRES_ATTENTION = "REQUIRES_ATTENTION"


class CommunicationChannel(StrEnum):
    EMAIL = "EMAIL"
    TEAMS = "TEAMS"  # reserved


class CommunicationDirection(StrEnum):
    OUTBOUND = "OUTBOUND"
    INBOUND = "INBOUND"


class CommunicationStatus(StrEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    DELIVERED = "DELIVERED"
    REPLIED = "REPLIED"


class ActorType(StrEnum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    SUPPLIER = "SUPPLIER"


class SpecialRequirementKind(StrEnum):
    SUPPLIER_INSTRUCTION = "SUPPLIER_INSTRUCTION"
    INTERNAL_NOTE = "INTERNAL_NOTE"


class EligibilityReason(StrEnum):
    """Why an employee is/isn't eligible for a cake order this birthday
    occurrence — computed centrally in ``app/services/eligibility_service.py``,
    never re-derived in the frontend (CLAUDE.md §7 backend-authorization
    rule applies equally to business eligibility, not just access control)."""

    ELIGIBLE = "ELIGIBLE"
    FUTURE_STARTER = "FUTURE_STARTER"
    INACTIVE_EMPLOYEE = "INACTIVE_EMPLOYEE"
    EMPLOYMENT_ENDED = "EMPLOYMENT_ENDED"
    MISSING_HIRE_DATE = "MISSING_HIRE_DATE"
    MISSING_BIRTHDAY = "MISSING_BIRTHDAY"
    INVALID_EMPLOYEE_DATA = "INVALID_EMPLOYEE_DATA"


class AddressVerificationStatus(StrEnum):
    """P&C-driven manual workflow status — never set by automation, never
    triggers outbound contact to the employee (plan requirement: no
    automatic employee contact). Tracked per ``BirthdayOrder`` because
    verification is only meaningful once an order exists to deliver to."""

    NOT_CHECKED = "NOT_CHECKED"
    VERIFICATION_REQUESTED = "VERIFICATION_REQUESTED"
    VERIFIED = "VERIFIED"
    NEEDS_UPDATE = "NEEDS_UPDATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
