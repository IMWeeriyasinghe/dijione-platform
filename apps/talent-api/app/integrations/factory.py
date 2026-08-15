from functools import lru_cache

from app.core.config import get_settings
from app.integrations.hubspot.client import HubSpotClient
from app.integrations.hubspot.mock_client import MockHubSpotClient
from app.integrations.lever.client import LeverClient
from app.integrations.lever.live_client import LiveLeverClient
from app.integrations.lever.mock_client import MockLeverClient


class IntegrationNotConfiguredError(Exception):
    pass


@lru_cache
def get_lever_client() -> LeverClient:
    settings = get_settings()
    if settings.integrations_mode == "mock" or not settings.lever_api_key:
        return MockLeverClient()
    # Read-only production client (CLAUDE.md §60 LIVE LEVER SAFETY
    # CONTRACT) — see live_client.py's module docstring for the
    # write-safety-by-construction guarantee.
    return LiveLeverClient()


@lru_cache
def get_hubspot_client() -> HubSpotClient:
    settings = get_settings()
    if settings.integrations_mode == "mock" or not settings.hubspot_access_token:
        return MockHubSpotClient()
    raise IntegrationNotConfiguredError(
        "Live HubSpotClient is not implemented in this phase — no "
        "HUBSPOT_ACCESS_TOKEN has been supplied. Set INTEGRATIONS_MODE=mock "
        "to continue using MockHubSpotClient."
    )
