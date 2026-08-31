"""Enumerations owned by the People / Workforce domain (BambooHR)."""

from enum import StrEnum

MODULE_BIRTHDAY = "birthday"
BIRTHDAY_ADMIN_ROLE = "BIRTHDAY_ADMIN"


class SyncStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


TERMINAL_STATUSES = frozenset({SyncStatus.SUCCEEDED, SyncStatus.PARTIAL, SyncStatus.FAILED})
ACTIVE_STATUSES = frozenset({SyncStatus.QUEUED, SyncStatus.RUNNING})


class SyncTriggerType(StrEnum):
    SCHEDULED = "SCHEDULED"
    AD_HOC = "AD_HOC"


class NotificationType(StrEnum):
    INTEGRATION_SYNC_FAILED = "INTEGRATION_SYNC_FAILED"
    PEOPLE_SYNC_COMPLETE = "PEOPLE_SYNC_COMPLETE"
