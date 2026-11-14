"""Diji On-site vocabulary (module-local; never imported by other services)."""

from enum import StrEnum

MODULE_ONSITE = "onsite"


class Perm(StrEnum):
    DASHBOARD_READ = "onsite.dashboard.read"
    ATTENDANCE_READ = "onsite.attendance.read"
    EXCEPTIONS_READ = "onsite.exceptions.read"
    HEALTH_READ = "onsite.health.read"
    IDENTITY_READ = "onsite.identity.read"
    IDENTITY_MANAGE = "onsite.identity.manage"
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
    """LEGACY vocabulary, kept only for the backward-compatible API contract.
    Values are now derived from the verified mapping's employee (never from
    Employee Number equality); UNMATCHED/AMBIGUOUS are never emitted."""

    MATCHED_ACTIVE = "MATCHED_ACTIVE"
    MATCHED_INACTIVE = "MATCHED_INACTIVE"
    MATCHED_BEFORE_HIRE = "MATCHED_BEFORE_HIRE"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"


class MappingStatus(StrEnum):
    """Identity of one ZKBioTime ID on one site-local day, resolved ONLY from
    administrator-verified mappings (never from Employee Number equality)."""

    MAPPED = "MAPPED"  # one verified mapping covers the day; employee is in the directory
    MAPPED_DIRECTORY_MISSING = "MAPPED_DIRECTORY_MISSING"  # verified, but bamboohr_id absent from the snapshot
    UNMAPPED = "UNMAPPED"  # no verified mapping covers the day -> hidden from viewer records
    MAPPING_CONFLICT = "MAPPING_CONFLICT"  # defensive: >1 verified mapping covers the day -> hidden
    DIRECTORY_UNAVAILABLE = "DIRECTORY_UNAVAILABLE"  # verified, but the directory could not be loaded


IDENTIFIED_STATUSES = frozenset({MappingStatus.MAPPED, MappingStatus.MAPPED_DIRECTORY_MISSING,
                                 MappingStatus.DIRECTORY_UNAVAILABLE})


class ReviewFlag(StrEnum):
    SINGLE_PUNCH = "SINGLE_PUNCH"
    HIGH_PUNCH_COUNT = "HIGH_PUNCH_COUNT"
    POSSIBLE_DUPLICATE_TAP = "POSSIBLE_DUPLICATE_TAP"
    UNMATCHED_CODE = "UNMATCHED_CODE"
    AMBIGUOUS_CODE = "AMBIGUOUS_CODE"
    INACTIVE_EMPLOYEE_ACTIVITY = "INACTIVE_EMPLOYEE_ACTIVITY"
    BEFORE_HIRE_ACTIVITY = "BEFORE_HIRE_ACTIVITY"
    TZ_INCONSISTENT = "TZ_INCONSISTENT"
