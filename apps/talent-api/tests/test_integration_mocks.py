"""HubSpot mock client (a stub until the Commercial/CRM domain is built).
Lever adapters + mapper moved to recruitment-api — see that service's suite.
"""

from app.integrations.hubspot.mock_client import MockHubSpotClient


def test_mock_hubspot_client_matches_demo_clients():
    client = MockHubSpotClient()
    companies = client.list_companies()
    names = {c.name for c in companies}
    assert {"ABC Company", "XYZ Company", "Nova Solutions"} <= names

    abc = next(c for c in companies if c.name == "ABC Company")
    assert len(client.list_contacts(abc.id)) > 0
    assert len(client.list_deals(abc.id)) > 0
