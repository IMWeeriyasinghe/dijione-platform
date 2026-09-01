from functools import lru_cache

from app.core.config import get_settings
from app.integrations.lever.client import LeverClient
from app.integrations.lever.live_client import LiveLeverClient
from app.integrations.lever.mock_client import MockLeverClient


@lru_cache
def get_lever_client() -> LeverClient:
    """The single constructor of the Lever client in all of DijiOne
    (Architecture Completion Plan §3). Mock unless a real key is configured
    outside INTEGRATIONS_MODE=mock. The live client is GET-only by
    construction — CLAUDE.md §60 LIVE LEVER SAFETY CONTRACT."""
    settings = get_settings()
    if settings.integrations_mode == "mock" or not settings.lever_api_key:
        return MockLeverClient()
    return LiveLeverClient()
