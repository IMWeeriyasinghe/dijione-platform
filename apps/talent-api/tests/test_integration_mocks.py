from app.core.constants import ApplicationStatus, CanonicalStage
from app.integrations.hubspot.mock_client import MockHubSpotClient
from app.integrations.lever.mapper import map_lever_archive_outcome, map_lever_stage
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

    assert len(client.list_stages()) == 14  # real tenant pipeline, live-discovery confirmed
    assert len(client.list_archive_reasons()) > 0
    assert len(client.list_users()) > 0
    assert client.list_applications(opportunities[0].id)[0].opportunity_id == opportunities[0].id
    # No structured interview/offer data was found for real sampled
    # opportunities during live discovery — the mock mirrors that (mostly
    # empty), not a fabricated fully-populated dataset.
    assert client.list_offers("opp-does-not-exist") == []


def test_lever_stage_mapping_matches_real_tenant_pipeline():
    # Real 14-stage pipeline (CLAUDE.md §60 live discovery), not a generic
    # assumption — see mapper.py for which entries are proposed defaults.
    assert map_lever_stage("New lead") == CanonicalStage.SOURCING
    assert map_lever_stage("Recruiter Phone Screen") == CanonicalStage.SCREENING
    assert map_lever_stage("SME Interview") == CanonicalStage.SCREENING
    assert map_lever_stage("Presented to Customer") == CanonicalStage.CLIENT_REVIEW
    assert map_lever_stage("Client Interview") == CanonicalStage.INTERVIEWS
    assert map_lever_stage("Offer") == CanonicalStage.OFFER
    # Unknown provider stage text must fall back safely, not raise.
    assert map_lever_stage("Some Brand New Lever Stage") == CanonicalStage.SOURCING


def test_lever_archive_outcome_mapping():
    # "Hired" is confirmed an Archive Reason, not a pipeline stage.
    assert map_lever_archive_outcome("Hired") == ApplicationStatus.HIRED
    assert map_lever_archive_outcome("Withdrew") == ApplicationStatus.WITHDRAWN
    assert map_lever_archive_outcome("Position closed") == ApplicationStatus.REJECTED
    assert map_lever_archive_outcome(None) == ApplicationStatus.REJECTED


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
