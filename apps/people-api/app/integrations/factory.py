from functools import lru_cache

from app.core.config import get_settings
from app.integrations.bamboohr.client import BambooHRClient
from app.integrations.bamboohr.mock_client import MockBambooHRClient
from app.integrations.bamboohr.workforce_client import BambooHRWorkforceClient
from app.integrations.bamboohr.workforce_mock_client import MockBambooHRWorkforceClient


@lru_cache
def get_bamboohr_client() -> BambooHRClient:
    """The single constructor of the BambooHR client in all of DijiOne
    (Architecture Completion Plan §3). Never write to BambooHR."""
    settings = get_settings()
    if settings.integrations_mode == "mock":
        return MockBambooHRClient()
    from app.integrations.bamboohr.http_client import BambooHRHttpClient

    return BambooHRHttpClient()  # raises BambooHRNotConfiguredError if unconfigured


@lru_cache
def get_bamboohr_workforce_client() -> BambooHRWorkforceClient:
    """Constructor of the generic Workforce Directory's BambooHR client —
    separate from ``get_bamboohr_client()`` (the Birthday-oriented Employee
    contract), which is unchanged. Never write to BambooHR."""
    settings = get_settings()
    if settings.integrations_mode == "mock":
        return MockBambooHRWorkforceClient()
    from app.integrations.bamboohr.workforce_http_client import BambooHRWorkforceHttpClient

    return BambooHRWorkforceHttpClient()  # raises WorkforceSourceNotConfiguredError if unconfigured
