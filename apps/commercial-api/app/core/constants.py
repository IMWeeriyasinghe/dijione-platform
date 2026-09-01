"""Enumerations owned by the Commercial / CRM domain (HubSpot — deferred)."""

from enum import StrEnum


class ProcessingStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED_DUPLICATE = "IGNORED_DUPLICATE"
    FAILED = "FAILED"
