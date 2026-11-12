"""Notifications and audit reach Platform Core best-effort, once per attempt.

There is deliberately no retry or outbox: the endpoint has no idempotency key,
so a retry after an ambiguous failure could send the same alert twice. A failed
delivery is logged and lost.
"""

import json

import httpx
import pytest
from auth_client_py import PlatformClient
from sqlalchemy import select

from app.models.application import Application
from app.services import application_service as application_module
from app.services import side_effects
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.side_effects import collect_side_effects, deliver_side_effects
from tests.test_client_access_security import _reconcile


@pytest.fixture()
def platform(monkeypatch):
    monkeypatch.undo()  # the autouse stub would hide the real HTTP behaviour
    return _platform


def _platform(handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(wrapped), base_url="http://platform.test")
    return PlatformClient(base_url="http://platform.test", internal_secret="s", caller="talent-api", client=client), calls


def _send(service):
    service.notify_module_role(module_key="talent-flow", role="TA_MEMBER", type="T", title="Hello", client_id=4)


def test_delivery_posts_the_notification_with_the_internal_token(platform):
    platform, calls = platform(lambda r: httpx.Response(201, json={}))
    _send(NotificationService(client=platform))
    assert calls[0].url.path == "/api/platform/internal/notifications/broadcast"
    assert calls[0].headers["X-Internal-Token"] == "s"
    assert json.loads(calls[0].content)["client_id"] == 4


def test_temporary_failure_is_not_fatal_and_is_attempted_once(platform):
    platform, calls = platform(lambda r: httpx.Response(503))
    _send(NotificationService(client=platform))
    assert len(calls) == 1


def test_platform_unreachable_is_not_fatal_for_audit_either(platform):
    def down(request):
        raise httpx.ConnectError("down", request=request)

    platform, calls = platform(down)
    AuditService(client=platform).log(actor_id=1, action="a", entity_type="E", entity_id=1)
    assert len(calls) == 1


def test_a_rolled_back_transaction_sends_nothing(platform):
    platform, calls = platform(lambda r: httpx.Response(201, json={}))
    with collect_side_effects() as effects:
        _send(NotificationService(client=platform))
    assert calls == [] and len(effects) == 1


@pytest.fixture()
def warnings_logged(monkeypatch):
    logged = []
    monkeypatch.setattr(side_effects.logger, "warning", lambda msg, *args: logged.append(msg % args))
    return logged


def test_one_failed_effect_does_not_stop_the_rest_and_is_reported(warnings_logged):
    delivered = []

    def bad():
        raise RuntimeError("no")

    deliver_side_effects([bad, lambda: delivered.append(1)], limit_seconds=5)
    assert delivered == [1]
    assert warnings_logged == ["side effects undelivered=1 reason=delivery_error"]


def test_time_limit_reports_what_was_not_sent(warnings_logged):
    delivered = []
    deliver_side_effects([lambda: delivered.append(1)], limit_seconds=-1)
    assert delivered == []
    assert warnings_logged == ["side effects undelivered=1 reason=time_limit"]


def test_repeat_reconcile_sends_no_duplicate_notifications(db, two_tenant_world, platform_calls):
    _reconcile(db, two_tenant_world["abc"].name)
    sent = len(platform_calls["notifications"]) + len(platform_calls["broadcasts"])
    _reconcile(db, two_tenant_world["abc"].name)
    assert len(platform_calls["notifications"]) + len(platform_calls["broadcasts"]) == sent


def test_sharing_a_candidate_notifies_only_that_client(db, two_tenant_world, monkeypatch):
    _reconcile(db, two_tenant_world["abc"].name)
    sent = []
    monkeypatch.setattr(
        application_module.NotificationService, "notify_module_role", lambda self, **kw: sent.append(kw)
    )
    application = db.execute(select(Application)).scalars().one()
    application_module.ApplicationService(db).update_visibility(
        application_id=application.id, actor_id=1, is_client_visible=True, client_visible_notes="ok"
    )
    assert [s["client_id"] for s in sent] == [two_tenant_world["abc"].id]
