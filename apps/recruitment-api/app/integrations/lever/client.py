"""LeverClient interface. ``LiveLeverClient`` (live_client.py) is the real,
read-only production implementation, wired in via
``app.integrations.factory.get_lever_client`` when ``LEVER_API_KEY`` is
configured outside mock mode. Every method here is a GET-only read — no
method on this interface, or any implementation of it, may issue a write
to Lever. Never write to Lever without separate, explicit authorization
(CLAUDE.md §60 LIVE LEVER SAFETY CONTRACT).
"""

from abc import ABC, abstractmethod

from app.integrations.lever.schemas import (
    LeverApplication,
    LeverArchiveReason,
    LeverInterview,
    LeverOfferSummary,
    LeverOpportunity,
    LeverPosting,
    LeverStage,
    LeverUser,
)


class LeverClient(ABC):
    @abstractmethod
    def list_postings(self) -> list[LeverPosting]: ...

    @abstractmethod
    def list_stages(self) -> list[LeverStage]: ...

    @abstractmethod
    def list_archive_reasons(self) -> list[LeverArchiveReason]: ...

    @abstractmethod
    def list_users(self) -> list[LeverUser]: ...

    @abstractmethod
    def list_opportunities(
        self, posting_id: str | None = None, limit: int | None = None
    ) -> list[LeverOpportunity]: ...

    @abstractmethod
    def get_opportunity(self, opportunity_id: str) -> LeverOpportunity | None: ...

    @abstractmethod
    def list_applications(self, opportunity_id: str) -> list[LeverApplication]: ...

    @abstractmethod
    def list_interviews(self, opportunity_id: str) -> list[LeverInterview]: ...

    @abstractmethod
    def list_offers(self, opportunity_id: str) -> list[LeverOfferSummary]: ...


class LeverNotConfiguredError(Exception):
    """Raised when no live Lever credential is configured and mock mode is
    not in effect — see ``app.integrations.factory.get_lever_client``."""
