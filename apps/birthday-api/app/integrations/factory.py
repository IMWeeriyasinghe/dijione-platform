from functools import lru_cache

from app.core.config import get_settings
from app.integrations.bamboohr.client import BambooHRClient
from app.integrations.bamboohr.mock_client import MockBambooHRClient
from app.integrations.graph_email.client import EmailClient
from app.integrations.graph_email.mock_client import MockGraphEmailClient


@lru_cache
def get_bamboohr_client() -> BambooHRClient:
    settings = get_settings()
    if settings.integrations_mode == "mock":
        return MockBambooHRClient()
    # Imported lazily so `httpx`-specific import/config errors don't surface
    # unless a live client is actually requested (mirrors get_email_client).
    from app.integrations.bamboohr.http_client import BambooHRHttpClient

    return BambooHRHttpClient()  # raises BambooHRNotConfiguredError if unconfigured


@lru_cache
def get_email_client() -> EmailClient:
    settings = get_settings()
    # email_sending_mode (not integrations_mode) gates this — BambooHR can
    # be live while email stays mocked during the dry-run phase (plan §7/§8).
    if settings.email_sending_mode == "mock":
        return MockGraphEmailClient()
    # Imported lazily so `httpx`/Graph-specific config errors don't surface
    # unless a live client is actually requested.
    from app.integrations.graph_email.graph_client import GraphEmailClient

    return GraphEmailClient()
