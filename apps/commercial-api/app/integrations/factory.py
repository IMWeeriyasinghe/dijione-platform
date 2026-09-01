from functools import lru_cache

from app.core.config import get_settings
from app.integrations.hubspot.client import HubSpotClient
from app.integrations.hubspot.mock_client import MockHubSpotClient


class IntegrationNotConfiguredError(Exception):
    pass


@lru_cache
def get_hubspot_client() -> HubSpotClient:
    """commercial-api is the single DijiOne owner of HubSpot when it is
    built (Architecture Completion Plan §3). Mock-only for now — no live
    client is implemented; read-only access has not been requested."""
    settings = get_settings()
    if settings.integrations_mode == "mock" or not settings.hubspot_access_token:
        return MockHubSpotClient()
    raise IntegrationNotConfiguredError(
        "Live HubSpotClient is not implemented — no HUBSPOT_ACCESS_TOKEN has "
        "been supplied. Set INTEGRATIONS_MODE=mock to continue using MockHubSpotClient."
    )
