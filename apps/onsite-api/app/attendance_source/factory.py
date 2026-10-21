from app.attendance_source.client import OnsiteSourceClient
from app.attendance_source.mock_client import MockOnsiteSource
from app.core.config import get_settings


def get_onsite_source() -> OnsiteSourceClient:
    """A fresh client per sync run (the live client holds one connection).
    Mock by default; ``INTEGRATIONS_MODE=live`` reads Azure SQL."""
    if get_settings().integrations_mode == "mock":
        return MockOnsiteSource()
    from app.attendance_source.sql_client import OnsiteSqlClient

    return OnsiteSqlClient()
