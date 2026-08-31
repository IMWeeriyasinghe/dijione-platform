"""HubSpotClient interface. HubSpot is the CRM/commercial system of record
(CLAUDE.md §25) — companies, contacts, deals only. Never infer the detailed
recruitment pipeline from HubSpot data.
"""

from abc import ABC, abstractmethod

from app.integrations.hubspot.schemas import HubSpotCompany, HubSpotContact, HubSpotDeal


class HubSpotClient(ABC):
    @abstractmethod
    def list_companies(self) -> list[HubSpotCompany]: ...

    @abstractmethod
    def get_company(self, company_id: str) -> HubSpotCompany | None: ...

    @abstractmethod
    def list_contacts(self, company_id: str) -> list[HubSpotContact]: ...

    @abstractmethod
    def list_deals(self, company_id: str) -> list[HubSpotDeal]: ...


class HubSpotNotConfiguredError(Exception):
    """Raised by a future live HubSpotClient when HUBSPOT_ACCESS_TOKEN is unset."""
