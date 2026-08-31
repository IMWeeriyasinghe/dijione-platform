from functools import lru_cache

from app.core.config import get_settings
from app.integrations.bamboohr.client import BambooHRClient
from app.integrations.bamboohr.mock_client import MockBambooHRClient


@lru_cache
def get_bamboohr_client() -> BambooHRClient:
    """The single constructor of the BambooHR client in all of DijiOne
    (Architecture Completion Plan §3). Never write to BambooHR."""
    settings = get_settings()
    if settings.integrations_mode == "mock":
        return MockBambooHRClient()
    from app.integrations.bamboohr.http_client import BambooHRHttpClient

    return BambooHRHttpClient()  # raises BambooHRNotConfiguredError if unconfigured
