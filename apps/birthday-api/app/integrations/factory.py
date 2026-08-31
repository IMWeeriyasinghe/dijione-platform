from functools import lru_cache

from app.core.config import get_settings
from app.integrations.graph_email.client import EmailClient
from app.integrations.graph_email.mock_client import MockGraphEmailClient
from app.integrations.people_source.client import EmployeeSourceClient
from app.integrations.people_source.mock_adapter import MockEmployeeSource


@lru_cache
def get_employee_source() -> EmployeeSourceClient:
    """birthday-api holds NO BambooHR credential (Architecture Completion
    Plan §3) — it consumes the People / Workforce domain (people-api) over
    HTTP. Mock by default; the real adapter calls people-api."""
    settings = get_settings()
    if settings.integrations_mode == "mock":
        return MockEmployeeSource()
    from app.integrations.people_source.http_adapter import PeopleApiEmployeeSource

    return PeopleApiEmployeeSource()


@lru_cache
def get_email_client() -> EmailClient:
    settings = get_settings()
    # email_sending_mode (not integrations_mode) gates this — People can
    # be live while email stays mocked during the dry-run phase (plan §7/§8).
    if settings.email_sending_mode == "mock":
        return MockGraphEmailClient()
    # Imported lazily so `httpx`/Graph-specific config errors don't surface
    # unless a live client is actually requested.
    from app.integrations.graph_email.graph_client import GraphEmailClient

    return GraphEmailClient()
