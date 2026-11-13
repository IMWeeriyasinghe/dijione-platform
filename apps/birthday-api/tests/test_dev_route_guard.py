"""DEV-only helper routes must fail closed outside APP_ENV=development.

Regression for the handover finding: /internal/dev/inbound-email was gated
only on EMAIL_SENDING_MODE=mock, and PROD runs with EMAIL_SENDING_MODE=mock,
so the injector was live in PROD (behind the internal token)."""

from __future__ import annotations

import pytest

INTERNAL = {"X-Internal-Token": "test-only-internal-secret"}
PAYLOAD = {"from_address": "supplier@example.com", "subject": "Re: order", "body": "ok"}


@pytest.fixture
def app_env(monkeypatch):
    from app.core.config import get_settings

    def _set(value: str | None, sending_mode: str = "mock") -> None:
        if value is None:
            monkeypatch.delenv("APP_ENV", raising=False)
        else:
            monkeypatch.setenv("APP_ENV", value)
        monkeypatch.setenv("EMAIL_SENDING_MODE", sending_mode)
        get_settings.cache_clear()

    yield _set
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("EMAIL_SENDING_MODE", raising=False)
    get_settings.cache_clear()


@pytest.mark.parametrize("env", ["prod", "uat", "production", "PROD", ""])
def test_inbound_injector_404_outside_development_even_in_mock_mode(api_client, db, app_env, env):
    app_env(env, sending_mode="mock")
    resp = api_client.post("/api/birthday/internal/dev/inbound-email", json=PAYLOAD, headers=INTERNAL)
    assert resp.status_code == 404


def test_inbound_injector_404_in_development_when_not_mock(api_client, db, app_env):
    app_env("development", sending_mode="graph")
    resp = api_client.post("/api/birthday/internal/dev/inbound-email", json=PAYLOAD, headers=INTERNAL)
    assert resp.status_code == 404


def test_inbound_injector_available_in_development_mock(api_client, db, app_env):
    app_env("development", sending_mode="mock")
    resp = api_client.post("/api/birthday/internal/dev/inbound-email", json=PAYLOAD, headers=INTERNAL)
    assert resp.status_code == 200
    assert "outcome" in resp.json()


def test_inbound_injector_still_requires_internal_token_in_development(api_client, db, app_env):
    app_env("development", sending_mode="mock")
    resp = api_client.post("/api/birthday/internal/dev/inbound-email", json=PAYLOAD)
    assert resp.status_code in (401, 403)


def test_prod_job_routes_unaffected(api_client, db, app_env):
    """The guard is per-route: PROD's scheduled-job endpoints keep working."""
    app_env("prod")
    resp = api_client.get("/api/birthday/internal/scan-runs", headers=INTERNAL)
    assert resp.status_code == 200
