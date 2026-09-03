"""VerifiedPostingPromotionReconciler — VERIFIED Lever postings become real
TalentRequest/Candidate/Application rows.

One VERIFIED posting = one TalentRequest. One unique Lever person = one
Candidate master. One Lever candidacy = one Application. Fail closed:
nothing promotes off an UNMAPPED/REJECTED posting; nothing is fabricated;
source-owned fields refresh on every run, TalentFlow-owned workflow state
never does.
"""

from app.core.constants import CanonicalStage
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.talent_request import TalentRequest
from app.repositories.application_repo import ApplicationRepository
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.services.application_service import ApplicationService
from app.services.posting_client_mapping_reconciler import PostingClientMappingReconciler
from app.services.recruitment_consumer_service import RecruitmentConsumerService
from app.services.verified_posting_promotion_reconciler import VerifiedPostingPromotionReconciler
from tests.conftest import FakeRecruitmentClient, recruitment_candidacy_dto, recruitment_posting_dto


def _dtc_ok(external_id, client_name, **kwargs):
    return recruitment_posting_dto(
        external_id, dtc_status="OK", dtc_client_name=client_name,
        dtc_raw_tag=f"DTC - {client_name}", **kwargs,
    )


def _verify(db, posting_dtos):
    """Run the DTC reconciler so each posting's mapping is VERIFIED (or
    not, for the deliberately-unresolved cases) and its RecruitmentPostingRef
    projection exists."""
    PostingClientMappingReconciler(db).reconcile_postings(posting_dtos)
    db.commit()


def _promote(db, candidacies=None):
    summary = VerifiedPostingPromotionReconciler(db).reconcile(candidacies=candidacies)
    db.commit()
    return summary


def test_verified_non_archived_posting_creates_one_talent_request(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name, title="Senior Engineer", location="Colombo")])

    summary = _promote(db, candidacies=[])
    assert summary.talent_requests_created == 1
    assert summary.verified_postings == 1

    tr = TalentRequestRepository(db).get_by_posting_external_id("p1")
    assert tr is not None
    assert tr.client_id == two_tenant_world["abc"].id
    assert tr.provider == "LEVER"
    assert tr.designation == "Senior Engineer"
    assert tr.location == "Colombo"
    assert tr.description == ""
    assert tr.current_stage == CanonicalStage.SOURCING.value
    assert tr.ta_status == "ATS_LINKED"
    assert tr.customer_success_status == "APPROVED"

    # Re-run: no new TalentRequest.
    second = _promote(db, candidacies=[])
    assert second.talent_requests_created == 0


def test_non_resolved_postings_promote_nothing(db, two_tenant_world):
    _verify(db, [
        recruitment_posting_dto("no-tag", dtc_status="NO_TAG"),
        recruitment_posting_dto("malformed", dtc_status="MALFORMED", dtc_raw_tag="DTC -"),
        recruitment_posting_dto(
            "multiple", dtc_status="MULTIPLE",
            dtc_raw_tags=[f"DTC - {two_tenant_world['abc'].name}", "DTC - Crofti"],
        ),
        _dtc_ok("unknown", "Nonexistent Client Co"),
    ])

    summary = _promote(db, candidacies=[])
    assert summary.talent_requests_created == 0
    assert summary.verified_postings == 0
    assert db.query(TalentRequest).count() == 0
    assert db.query(Candidate).count() == 0
    assert db.query(Application).count() == 0


def test_candidacy_creates_candidate_and_application(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name)])
    candidacy = recruitment_candidacy_dto(
        "opp-1", posting_external_id="p1", candidate_external_id="contact-1",
        candidate_name="Jane Doe", candidate_email="jane@example.com",
        candidate_headline="Senior Backend Engineer", current_stage="SCREENING",
        status="ACTIVE",
    )

    summary = _promote(db, candidacies=[candidacy])
    assert summary.candidates_created == 1
    assert summary.applications_created == 1

    candidate = CandidateRepository(db).get_by_lever_external_id("contact-1")
    assert candidate is not None
    assert candidate.full_name == "Jane Doe"
    assert candidate.email == "jane@example.com"
    assert candidate.professional_title == "Senior Backend Engineer"
    assert candidate.summary == ""
    assert candidate.source == "LEVER"
    assert candidate.availability_status == "IN_PROCESS"

    tr = TalentRequestRepository(db).get_by_posting_external_id("p1")
    application = ApplicationRepository(db).get_for_pair(candidate.id, tr.id)
    assert application is not None
    assert application.lever_opportunity_id == "opp-1"
    assert application.current_stage == "SCREENING"
    assert application.is_client_visible is False


def test_second_run_creates_zero_new_rows(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name)])
    candidacy = recruitment_candidacy_dto(
        "opp-1", posting_external_id="p1", candidate_external_id="contact-1"
    )

    first = _promote(db, candidacies=[candidacy])
    assert first.talent_requests_created == 1
    assert first.candidates_created == 1
    assert first.applications_created == 1

    second = _promote(db, candidacies=[candidacy])
    assert second.talent_requests_created == 0
    assert second.candidates_created == 0
    assert second.applications_created == 0


def test_source_refresh_does_not_overwrite_application_workflow_state(db, two_tenant_world):
    # Stage/status are Lever facts and are refreshed from the source on
    # every reconcile (monitoring-first iteration); score has no
    # authoritative source and is never written. Only TalentFlow-owned
    # curation state (is_client_visible/client_visible_notes) must survive
    # a source refresh untouched.
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name)])
    candidacy = recruitment_candidacy_dto(
        "opp-1", posting_external_id="p1", candidate_external_id="contact-1",
        current_stage="SCREENING", status="ACTIVE",
    )
    _promote(db, candidacies=[candidacy])

    candidate = CandidateRepository(db).get_by_lever_external_id("contact-1")
    tr = TalentRequestRepository(db).get_by_posting_external_id("p1")
    application = ApplicationRepository(db).get_for_pair(candidate.id, tr.id)
    # score/recruiter_notes have no product write path any more — set
    # directly, purely to prove a source refresh never touches them.
    application.score = 8.5
    application.recruiter_notes = "Strong candidate."
    ApplicationService(db).update_visibility(
        application_id=application.id, actor_id=two_tenant_world["ta_user_id"],
        is_client_visible=True, client_visible_notes="Great fit.",
    )
    db.commit()

    advanced_candidacy = recruitment_candidacy_dto(
        "opp-1", posting_external_id="p1", candidate_external_id="contact-1",
        current_stage="INTERVIEWS", status="SHORTLISTED", lever_archive_reason="Withdrew",
    )
    _promote(db, candidacies=[advanced_candidacy])

    db.refresh(application)
    assert application.current_stage == "INTERVIEWS"
    assert application.status == "SHORTLISTED"
    assert application.lever_archive_reason == "Withdrew"
    assert application.score == 8.5
    assert application.recruiter_notes == "Strong candidate."
    assert application.is_client_visible is True
    assert application.client_visible_notes == "Great fit."


def test_source_refresh_does_not_reset_talent_request_workflow(db, two_tenant_world):
    from app.services.talent_request_service import TalentRequestService

    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name, title="Original Title")])
    _promote(db, candidacies=[])

    tr = TalentRequestRepository(db).get_by_posting_external_id("p1")
    TalentRequestService(db).update_stage(
        request_id=tr.id, actor_id=two_tenant_world["ta_user_id"], stage="INTERVIEWS",
        client_safe_status_text=None,
    )
    TalentRequestService(db).update_ta_status(
        request_id=tr.id, actor_id=two_tenant_world["ta_user_id"], ta_status="IN_PROGRESS",
    )
    db.commit()

    _verify(db, [_dtc_ok("p1", name, title="Updated Title")])
    _promote(db, candidacies=[])

    db.refresh(tr)
    assert tr.current_stage == "INTERVIEWS"
    assert tr.ta_status == "IN_PROGRESS"
    assert tr.designation == "Updated Title"


def test_one_person_two_postings_one_candidate_two_applications(db, two_tenant_world):
    abc, xyz = two_tenant_world["abc"].name, two_tenant_world["xyz"].name
    _verify(db, [_dtc_ok("p1", abc), _dtc_ok("p2", xyz)])
    candidacies = [
        recruitment_candidacy_dto("opp-1", posting_external_id="p1", candidate_external_id="contact-1"),
        recruitment_candidacy_dto("opp-2", posting_external_id="p2", candidate_external_id="contact-1"),
    ]

    summary = _promote(db, candidacies=candidacies)
    assert summary.candidates_created == 1
    assert summary.applications_created == 2
    assert db.query(Candidate).count() == 1


def test_two_opportunities_same_person_same_posting_collapse_to_one_application(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name)])
    candidacies = [
        recruitment_candidacy_dto(
            "opp-early", posting_external_id="p1", candidate_external_id="contact-1",
            current_stage="SOURCING", synced_at="2026-01-01T00:00:00+00:00",
        ),
        recruitment_candidacy_dto(
            "opp-later", posting_external_id="p1", candidate_external_id="contact-1",
            current_stage="INTERVIEWS", synced_at="2026-02-01T00:00:00+00:00",
        ),
    ]

    summary = _promote(db, candidacies=candidacies)
    assert summary.collapsed_duplicate_candidacies == 1
    assert summary.applications_created == 1
    assert db.query(Application).count() == 1
    application = db.query(Application).one()
    assert application.current_stage == "INTERVIEWS"
    assert application.lever_opportunity_id == "opp-later"

    # Re-run stays collapsed to the same single Application.
    second = _promote(db, candidacies=candidacies)
    assert second.applications_created == 0
    assert db.query(Application).count() == 1


def test_candidacy_for_unverified_posting_is_skipped(db, two_tenant_world):
    _verify(db, [_dtc_ok("p1", "Nonexistent Client Co")])  # stays UNMAPPED
    candidacy = recruitment_candidacy_dto(
        "opp-1", posting_external_id="p1", candidate_external_id="contact-1"
    )

    summary = _promote(db, candidacies=[candidacy])
    assert summary.candidacies_skipped_no_verified_request == 1
    assert db.query(Candidate).count() == 0
    assert db.query(Application).count() == 0


def test_two_blank_email_candidates_do_not_collide(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name)])
    candidacies = [
        recruitment_candidacy_dto(
            "opp-1", posting_external_id="p1", candidate_external_id="contact-1",
            candidate_email="",
        ),
        recruitment_candidacy_dto(
            "opp-2", posting_external_id="p1", candidate_external_id="contact-2",
            candidate_email="",
        ),
    ]

    summary = _promote(db, candidacies=candidacies)
    assert summary.candidates_created == 2
    assert db.query(Candidate).count() == 2
    emails = {c.email for c in db.query(Candidate).all()}
    assert emails == {None}


def test_promotion_wired_into_consumer_return_dict(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    fake = FakeRecruitmentClient(
        postings=[_dtc_ok("p1", name)],
        candidacies=[recruitment_candidacy_dto(
            "opp-1", posting_external_id="p1", candidate_external_id="contact-1"
        )],
    )
    result = RecruitmentConsumerService(db, client=fake).refresh_projection_and_reconcile()

    assert result["refreshed"] is True
    assert result["promotion"]["talent_requests_created"] == 1
    assert result["promotion"]["candidates_created"] == 1
    assert result["promotion"]["applications_created"] == 1
    assert result["promotion"]["candidacies_available"] is True


def test_candidacy_fetch_failure_still_ensures_talent_requests(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    good = FakeRecruitmentClient(
        postings=[_dtc_ok("p1", name)],
        candidacies=[recruitment_candidacy_dto(
            "opp-1", posting_external_id="p1", candidate_external_id="contact-1"
        )],
    )
    RecruitmentConsumerService(db, client=good).refresh_projection_and_reconcile()

    candidate = CandidateRepository(db).get_by_lever_external_id("contact-1")
    tr = TalentRequestRepository(db).get_by_posting_external_id("p1")
    application = ApplicationRepository(db).get_for_pair(candidate.id, tr.id)
    ApplicationService(db).update_visibility(
        application_id=application.id, actor_id=two_tenant_world["ta_user_id"],
        is_client_visible=True, client_visible_notes="Visible now.",
    )
    db.commit()

    down = FakeRecruitmentClient(postings=[_dtc_ok("p1", name)], candidacies_down=True)
    result = RecruitmentConsumerService(db, client=down).refresh_projection_and_reconcile()

    assert result["refreshed"] is True
    assert result["promotion"]["candidacies_available"] is False
    assert result["promotion"]["candidates_created"] == 0
    assert result["promotion"]["applications_created"] == 0
    assert db.query(TalentRequest).count() == 1

    db.refresh(application)
    assert application.is_client_visible is True
    assert application.client_visible_notes == "Visible now."


def test_archived_verified_posting_gets_no_new_tr(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name, archived=True)])

    summary = _promote(db, candidacies=[])
    assert summary.talent_requests_created == 0
    assert TalentRequestRepository(db).get_by_posting_external_id("p1") is None

    # An existing TalentRequest for a posting that later gets archived is
    # kept and still receives source-fact refresh.
    _verify(db, [_dtc_ok("p2", name, archived=False, title="Kept Role")])
    _promote(db, candidacies=[])
    tr = TalentRequestRepository(db).get_by_posting_external_id("p2")
    assert tr is not None

    _verify(db, [_dtc_ok("p2", name, archived=True, title="Kept Role Renamed")])
    summary2 = _promote(db, candidacies=[])
    assert summary2.talent_requests_created == 0
    db.refresh(tr)
    assert tr.designation == "Kept Role Renamed"


def test_new_talent_request_route_still_403_after_promotion(api_client, db, two_tenant_world):
    name = two_tenant_world["abc"].name
    _verify(db, [_dtc_ok("p1", name)])
    _promote(db, candidacies=[])
    assert db.query(TalentRequest).count() == 1

    for headers in (
        two_tenant_world["abc_headers"], two_tenant_world["ta_headers"], two_tenant_world["cs_headers"],
    ):
        resp = api_client.post(
            "/api/talent/requests", headers=headers,
            json={"designation": "x", "description": "x", "required_skills": []},
        )
        assert resp.status_code == 403
