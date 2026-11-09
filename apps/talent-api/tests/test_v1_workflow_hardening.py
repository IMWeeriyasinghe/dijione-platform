"""Workflow rules and truthful counts for the V1 staff and client views."""

import pytest
from sqlalchemy import select

from app.models.application import Application
from app.models.interview import Interview
from app.schemas.application import ApplicationCreate
from app.services import message_service as message_module
from app.services.application_service import (
    ApplicationService,
    CandidateNotFoundError,
    InvalidApplicationValueError,
)
from app.services.message_service import MessageService
from app.services.talent_request_service import InvalidTransitionError, TalentRequestService
from tests.test_client_access_security import REQUESTS, _interview, _reconcile, _request, _share_all


@pytest.fixture()
def world(db, two_tenant_world):
    _reconcile(db, two_tenant_world["abc"].name)
    _share_all(db)
    return two_tenant_world


def _application(db) -> Application:
    return db.execute(select(Application)).scalars().one()


def test_client_workspace_hides_staff_fields_and_unshared_counts(api_client, db, world):
    url = f"{REQUESTS}/{_request(db, world['abc']).id}"
    shared = api_client.get(url, headers=world["abc_headers"]).json()
    assert shared["active_application_count"] == 1
    assert (shared["notes"], shared["ta_status"], shared["customer_success_status"], shared["priority"]) == ("", "", "", "")

    _application(db).is_client_visible = False
    db.commit()
    assert api_client.get(url, headers=world["abc_headers"]).json()["active_application_count"] == 0
    assert api_client.get(REQUESTS, headers=world["abc_headers"]).json()[0]["active_application_count"] == 0


def test_staff_keep_the_workflow_fields(api_client, db, world):
    url = f"{REQUESTS}/{_request(db, world['abc']).id}"
    body = api_client.get(url, headers=world["ta_headers"]).json()
    assert body["ta_status"] == "ATS_LINKED" and body["customer_success_status"] == "APPROVED"


def test_a_decided_request_cannot_be_reviewed_again(db, world):
    with pytest.raises(InvalidTransitionError):
        TalentRequestService(db).review_request(
            request_id=_request(db, world["abc"]).id, actor_id=1, decision="REJECTED", reason="late"
        )


def test_unknown_ta_status_is_rejected(db, world):
    with pytest.raises(InvalidTransitionError):
        TalentRequestService(db).update_ta_status(
            request_id=_request(db, world["abc"]).id, actor_id=1, ta_status="MADE_UP"
        )


def test_add_candidate_validates_stage_and_candidate(db, world):
    service = ApplicationService(db)
    request_id = _request(db, world["abc"]).id
    candidate_id = _application(db).candidate_id
    with pytest.raises(InvalidApplicationValueError):
        service.create_application(
            actor_id=1,
            payload=ApplicationCreate(candidate_id=candidate_id, talent_request_id=request_id, current_stage="NOPE"),
        )
    with pytest.raises(CandidateNotFoundError):
        service.create_application(
            actor_id=1, payload=ApplicationCreate(candidate_id=99999, talent_request_id=request_id)
        )


def test_lever_offer_stage_counts_as_an_offer(api_client, db, world):
    application = _application(db)
    application.current_stage, application.status = "OFFER", "ACTIVE"
    db.commit()
    dashboard = api_client.get("/api/talent/dashboard/client", headers=world["abc_headers"]).json()
    assert dashboard["offers_in_progress"] == 1
    assert dashboard["requests"][0]["ta_status"] == ""


def test_cancelled_interview_is_not_counted(api_client, db, world):
    _interview(db)
    url = "/api/talent/dashboard/client"
    assert api_client.get(url, headers=world["abc_headers"]).json()["interviews_this_week"] == 1
    db.execute(select(Interview)).scalars().one().status = "CANCELLED"
    db.commit()
    assert api_client.get(url, headers=world["abc_headers"]).json()["interviews_this_week"] == 0


def test_message_is_audited_without_its_body(db, world, platform_calls, monkeypatch):
    logged = []
    monkeypatch.setattr(message_module.AuditService, "log", lambda self, **kw: logged.append(kw))
    MessageService(db).send_message(
        talent_request_id=_request(db, world["abc"]).id, sender_id=7, sender_name="A", sender_role="TA_MEMBER", body="secret text"
    )
    assert logged[0]["action"] == "message.sent" and logged[0]["actor_id"] == 7
    assert "secret text" not in str(logged)
