"""Enumerations owned by the Recruitment Source domain (Lever).

This is the single DijiOne owner of direct Lever access (Architecture
Completion Plan §3). Consuming applications (DijiTalentFlow today, DijiSpark
later) receive the canonical DTOs this service exposes — never Lever's own
vocabulary.
"""

from enum import StrEnum

# Notification targeting for scheduled-sync failures — platform-api owns
# UserModuleRole, so recruitment-api sends module_key/role strings.
MODULE_TALENT_FLOW = "talent-flow"
TA_MANAGER_ROLE = "TA_MANAGER"


class CanonicalStage(StrEnum):
    """Client-facing canonical recruitment stages. Lever's own stage names
    are mapped into this fixed set by ``integrations/lever/mapper.py``."""

    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    REQUIREMENT_CONFIRMED = "REQUIREMENT_CONFIRMED"
    SOURCING = "SOURCING"
    SCREENING = "SCREENING"
    CLIENT_REVIEW = "CLIENT_REVIEW"
    INTERVIEWS = "INTERVIEWS"
    OFFER = "OFFER"
    ONBOARDING = "ONBOARDING"
    DEPLOYED = "DEPLOYED"


class ApplicationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SHORTLISTED = "SHORTLISTED"
    CLIENT_REVIEW = "CLIENT_REVIEW"
    OFFER = "OFFER"
    HIRED = "HIRED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class IntegrationProvider(StrEnum):
    LEVER = "LEVER"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    ERROR = "ERROR"


class ProcessingStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED_DUPLICATE = "IGNORED_DUPLICATE"
    FAILED = "FAILED"


class NotificationType(StrEnum):
    INTEGRATION_SYNC_FAILED = "INTEGRATION_SYNC_FAILED"
    RECRUITMENT_SYNC_COMPLETE = "RECRUITMENT_SYNC_COMPLETE"
