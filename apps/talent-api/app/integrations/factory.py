from functools import lru_cache

from app.core.config import get_settings
from app.integrations.hubspot.client import HubSpotClient
from app.integrations.hubspot.mock_client import MockHubSpotClient


class IntegrationNotConfiguredError(Exception):
    pass


# Lever is owned by the Recruitment Source domain (recruitment-api) —
# talent-api has NO direct Lever client (Architecture Completion Plan §3,
# CLAUDE.md data-ownership rule 5). It consumes postings/candidacies over
# the recruitment-api HTTP contract (auth_client_py.RecruitmentSourceClient).


@lru_cache
def get_hubspot_client() -> HubSpotClient:
    """HubSpot stays a mock-only stub here for now; the live client belongs
    to the Commercial/CRM domain (Wave F relocates this)."""
    settings = get_settings()
    if settings.integrations_mode == "mock" or not settings.hubspot_access_token:
        return MockHubSpotClient()
    raise IntegrationNotConfiguredError(
        "Live HubSpotClient is not implemented in this phase — no "
        "HUBSPOT_ACCESS_TOKEN has been supplied. Set INTEGRATIONS_MODE=mock "
        "to continue using MockHubSpotClient."
    )
