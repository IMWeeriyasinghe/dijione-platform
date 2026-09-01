"""MockLeverClient shape + stage/archive-reason mapper — mirrors the real
Dijital Team Lever tenant confirmed by live read-only discovery.
"""

from app.core.constants import ApplicationStatus, CanonicalStage
from app.integrations.lever.mapper import map_lever_archive_outcome, map_lever_stage
from app.integrations.lever.mock_client import MockLeverClient


def test_mock_lever_client_returns_realistic_shape():
    client = MockLeverClient()
    assert len(client.list_postings()) > 0

    opps = client.list_opportunities()
    assert len(opps) > 0
    assert client.get_opportunity(opps[0].id).id == opps[0].id
    assert client.get_opportunity("does-not-exist") is None

    assert len(client.list_stages()) == 14  # real 14-stage pipeline
    assert len(client.list_archive_reasons()) > 0
    assert len(client.list_users()) > 0
    assert client.list_applications(opps[0].id)[0].opportunity_id == opps[0].id
    assert client.list_offers("opp-nope") == []


def test_lever_stage_mapping_matches_real_tenant_pipeline():
    assert map_lever_stage("New lead") == CanonicalStage.SOURCING
    assert map_lever_stage("Recruiter Phone Screen") == CanonicalStage.SCREENING
    assert map_lever_stage("SME Interview") == CanonicalStage.SCREENING
    assert map_lever_stage("Presented to Customer") == CanonicalStage.CLIENT_REVIEW
    assert map_lever_stage("Client Interview") == CanonicalStage.INTERVIEWS
    assert map_lever_stage("Offer") == CanonicalStage.OFFER
    assert map_lever_stage("Some Brand New Lever Stage") == CanonicalStage.SOURCING


def test_lever_archive_outcome_mapping():
    assert map_lever_archive_outcome("Hired") == ApplicationStatus.HIRED
    assert map_lever_archive_outcome("Withdrew") == ApplicationStatus.WITHDRAWN
    assert map_lever_archive_outcome("Position closed") == ApplicationStatus.REJECTED
    assert map_lever_archive_outcome(None) == ApplicationStatus.REJECTED
