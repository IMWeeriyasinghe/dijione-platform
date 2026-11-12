"""Diji On-site vocabulary (module-local; never imported by other services)."""

from enum import StrEnum

MODULE_ONSITE = "onsite"


class Perm(StrEnum):
    DASHBOARD_READ = "onsite.dashboard.read"
    ATTENDANCE_READ = "onsite.attendance.read"
    EXCEPTIONS_READ = "onsite.exceptions.read"
    HEALTH_READ = "onsite.health.read"
    IDENTITY_READ = "onsite.identity.read"
    SYNC_REQUEST = "onsite.sync.request"
    SITES_MANAGE = "onsite.sites.manage"


class SyncStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


ACTIVE_STATUSES = frozenset({SyncStatus.QUEUED, SyncStatus.RUNNING})


class SyncTriggerType(StrEnum):
    SCHEDULED = "SCHEDULED"
    AD_HOC = "AD_HOC"


class FeedState(StrEnum):
    FRESH = "FRESH"
    DELAYED = "DELAYED"
    STALE = "STALE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_SYNCED = "NOT_SYNCED"


class IdentityClass(StrEnum):
    MATCHED_ACTIVE = "MATCHED_ACTIVE"
    MATCHED_INACTIVE = "MATCHED_INACTIVE"
    MATCHED_BEFORE_HIRE = "MATCHED_BEFORE_HIRE"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"


class ReviewFlag(StrEnum):
    SINGLE_PUNCH = "SINGLE_PUNCH"
    HIGH_PUNCH_COUNT = "HIGH_PUNCH_COUNT"
    POSSIBLE_DUPLICATE_TAP = "POSSIBLE_DUPLICATE_TAP"
    UNMATCHED_CODE = "UNMATCHED_CODE"
    AMBIGUOUS_CODE = "AMBIGUOUS_CODE"
    INACTIVE_EMPLOYEE_ACTIVITY = "INACTIVE_EMPLOYEE_ACTIVITY"
    BEFORE_HIRE_ACTIVITY = "BEFORE_HIRE_ACTIVITY"
    TZ_INCONSISTENT = "TZ_INCONSISTENT"
