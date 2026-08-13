from app.core.constants import CanonicalStage
from app.integrations.hubspot.mock_client import MockHubSpotClient
from app.integrations.lever.mapper import map_lever_stage
from app.integrations.lever.mock_client import MockLeverClient


def test_mock_lever_client_returns_realistic_shape():
    client = MockLeverClient()
    postings = client.list_postings()
    assert len(postings) > 0

    opportunities = client.list_opportunities()
    assert len(opportunities) > 0
    opp = client.get_opportunity(opportunities[0].id)
    assert opp is not None
    assert opp.id == opportunities[0].id

    assert client.get_opportunity("does-not-exist") is None


def test_lever_stage_mapping_never_leaks_provider_vocabulary():
    assert map_lever_stage("Client Review") == CanonicalStage.CLIENT_REVIEW
    assert map_lever_stage("Onsite Interview") == CanonicalStage.INTERVIEWS
    assert map_lever_stage("Hired") == CanonicalStage.ONBOARDING
    # Unknown provider stage text must fall back safely, not raise.
    assert map_lever_stage("Some Brand New Lever Stage") == CanonicalStage.SOURCING


def test_mock_hubspot_client_matches_demo_clients():
    client = MockHubSpotClient()
    companies = client.list_companies()
    names = {c.name for c in companies}
    assert {"ABC Company", "XYZ Company", "Nova Solutions"} <= names

    abc = next(c for c in companies if c.name == "ABC Company")
    contacts = client.list_contacts(abc.id)
    assert len(contacts) > 0
    deals = client.list_deals(abc.id)
    assert len(deals) > 0
