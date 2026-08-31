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


class ScanRunStatus(StrEnum):
    """Outcome of one run_daily_scan execution (Architecture Completion
    Plan Wave E). DEFERRED_SOURCE_UNAVAILABLE means people-api could not be
    reached at all — no employees were scanned, no orders were created or
    touched, and the next scan (which recomputes each employee's *next*
    occurrence from today) naturally catches up once the source recovers,
    as long as it happens within the configured scan lookahead window."""

    COMPLETED = "COMPLETED"
    DEFERRED_SOURCE_UNAVAILABLE = "DEFERRED_SOURCE_UNAVAILABLE"


class LeadTimeClass(StrEnum):
    NORMAL = "NORMAL"
    SHORT_NOTICE = "SHORT_NOTICE"
    URGENT = "URGENT"


class OrderStatus(StrEnum):
    """Optimized future-state state machine (DijiBirthday semi-automation
    plan §P). "Verification is the approval": a standard order goes
    PENDING_VERIFICATION -> SENT_TO_SUPPLIER automatically the moment a
    human marks the address VERIFIED; only orders carrying an exception
    trigger route through REQUIRES_REVIEW for a one-click human confirm.
    Legacy DRAFT/READY_FOR_APPROVAL/APPROVED/PLANNED/REJECTED/
    SUPPLIER_REVIEW statuses have been retired — there is no persisted
    production data to migrate (dev-only SQLite, mock integrations)."""

    PENDING_VERIFICATION = "PENDING_VERIFICATION"  # the one routine human gate
    REQUIRES_REVIEW = "REQUIRES_REVIEW"  # flagged order awaiting one-click confirm & release
    REQUIRES_ATTENTION = "REQUIRES_ATTENTION"  # typed exception queue
    ON_HOLD = "ON_HOLD"
    SENT_TO_SUPPLIER = "SENT_TO_SUPPLIER"
    CHANGE_REQUESTED = "CHANGE_REQUESTED"
    CONFIRMED = "CONFIRMED"  # supplier accepted (merged acknowledge+confirm)
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"  # auto-set by the system the moment DELIVERED lands
    UNABLE_TO_FULFIL = "UNABLE_TO_FULFIL"
    CANCELLED = "CANCELLED"


class ExceptionReason(StrEnum):
    """Typed reason an order landed in REQUIRES_ATTENTION or was flagged
    into REQUIRES_REVIEW — drives the exception/review queues and
    dashboard drilldowns (plan §Q)."""

    MISSING_EMAIL = "MISSING_EMAIL"
    NO_SUPPLIER = "NO_SUPPLIER"
    NO_DEFAULT_CAKE = "NO_DEFAULT_CAKE"
    SHORT_NOTICE_LEAD_TIME = "SHORT_NOTICE_LEAD_TIME"
    ADDRESS_MANUALLY_CORRECTED = "ADDRESS_MANUALLY_CORRECTED"
    DELIVERY_DATE_CHANGED = "DELIVERY_DATE_CHANGED"
    QUANTITY_CHANGED = "QUANTITY_CHANGED"
    CAKE_OVERRIDDEN = "CAKE_OVERRIDDEN"
    SUPPLIER_OVERRIDDEN = "SUPPLIER_OVERRIDDEN"
    SEND_FAILED = "SEND_FAILED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    SUPPLIER_CANNOT_FULFIL = "SUPPLIER_CANNOT_FULFIL"


class OrderIssueType(StrEnum):
    CHANGE_REQUEST = "CHANGE_REQUEST"
    CANNOT_FULFIL = "CANNOT_FULFIL"
    DELIVERY_ISSUE = "DELIVERY_ISSUE"
    OTHER = "OTHER"


class OrderIssueStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


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
