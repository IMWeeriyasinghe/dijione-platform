"""LeverClient interface. Production implementation (not built during this
phase — no credentials available, CLAUDE.md §58/§60) will call Lever's REST
API read-only with LEVER_API_KEY. Never write to Lever without explicit
authorization.
"""

from abc import ABC, abstractmethod

from app.integrations.lever.schemas import (
    LeverInterview,
    LeverOpportunity,
    LeverPosting,
    LeverStage,
)


class LeverClient(ABC):
    @abstractmethod
    def list_postings(self) -> list[LeverPosting]: ...

    @abstractmethod
    def list_stages(self) -> list[LeverStage]: ...

    @abstractmethod
    def list_opportunities(self, posting_id: str | None = None) -> list[LeverOpportunity]: ...

    @abstractmethod
    def get_opportunity(self, opportunity_id: str) -> LeverOpportunity | None: ...

    @abstractmethod
    def list_interviews(self, opportunity_id: str) -> list[LeverInterview]: ...


class LeverNotConfiguredError(Exception):
    """Raised by a future live LeverClient when LEVER_API_KEY is unset."""
