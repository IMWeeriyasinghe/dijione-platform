"""Authorization: On-site role required; permissions per route; fail-closed
site allow-list (unknown/disabled site -> 404); audited site changes."""

from tests.conftest import enable_site, headers_for, run_sync

ADMIN_GETS = ["/api/onsite/admin/sites", "/api/onsite/admin/sites/dev-site", "/api/onsite/admin/health",
              "/api/onsite/admin/identity-match", "/api/onsite/sync/history"]


def test_no_token_401_and_no_onsite_role_403(api_client, db):
    assert api_client.get("/api/onsite/freshness").status_code == 401
    assert api_client.get("/api/onsite/freshness", headers=headers_for(role=None)).status_code == 403
    assert api_client.get("/api/onsite/summary", headers=headers_for(role=None)).status_code == 403


def test_metadata_is_public(api_client, db):
    assert api_client.get("/api/onsite/metadata").json()["key"] == "onsite"


def test_viewer_cannot_use_admin_endpoints(api_client, db, audit_calls):
    run_sync(api_client)
    viewer = headers_for("ONSITE_VIEWER")
    for path in ADMIN_GETS:
        assert api_client.get(path, headers=viewer).status_code == 403, path
    assert api_client.put("/api/onsite/admin/sites/dev-site", json={"enabled": True}, headers=viewer).status_code == 403
    assert api_client.post("/api/onsite/sync", headers=viewer).status_code == 403
    assert api_client.get("/api/onsite/freshness", headers=viewer).status_code == 200


def test_admin_can_use_admin_endpoints(api_client, db, audit_calls, directory):
    run_sync(api_client)
    admin = headers_for("ONSITE_ADMIN")
    for path in ADMIN_GETS:
        assert api_client.get(path, headers=admin).status_code == 200, path


def test_sites_disabled_by_default_and_invisible(api_client, db):
    run_sync(api_client)
    viewer = headers_for("ONSITE_VIEWER")
    assert api_client.get("/api/onsite/freshness", headers=viewer).json()["sites"] == []
    assert api_client.get("/api/onsite/freshness?site_id=dev-site", headers=viewer).status_code == 404
    assert api_client.get("/api/onsite/summary", headers=viewer).json()["mirrored_events"] == 0


def test_enable_site_via_admin_action_is_audited(api_client, db, audit_calls):
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    assert audit_calls[-1]["action"] == "onsite.site.enabled"
    assert audit_calls[-1]["previous"]["enabled"] is False and audit_calls[-1]["new"]["enabled"] is True

    viewer = headers_for("ONSITE_VIEWER")
    sites = api_client.get("/api/onsite/freshness", headers=viewer).json()["sites"]
    assert [s["site_id"] for s in sites] == ["dev-site"]
    assert "agent" not in sites[0]  # technical fields are admin-only
    assert api_client.get("/api/onsite/freshness?site_id=dev-site", headers=viewer).status_code == 200
    assert api_client.get("/api/onsite/freshness?site_id=syd-site", headers=viewer).status_code == 404  # still disabled
    assert api_client.get("/api/onsite/summary", headers=viewer).json()["mirrored_events"] == 10

    api_client.put("/api/onsite/admin/sites/dev-site", json={"enabled": False}, headers=headers_for())
    assert audit_calls[-1]["action"] == "onsite.site.disabled"
    assert api_client.get("/api/onsite/freshness?site_id=dev-site", headers=viewer).status_code == 404


def test_unknown_site_404_everywhere(api_client, db, audit_calls):
    run_sync(api_client)
    admin = headers_for("ONSITE_ADMIN")
    assert api_client.get("/api/onsite/admin/sites/no-such-site", headers=admin).status_code == 404
    assert api_client.put("/api/onsite/admin/sites/no-such-site", json={"enabled": True}, headers=admin).status_code == 404
    assert api_client.get("/api/onsite/freshness?site_id=no-such-site", headers=admin).status_code == 404


def test_freshness_states(api_client, db, audit_calls, monkeypatch):
    from datetime import UTC, datetime, timedelta

    import app.services.freshness_service as fs
    from app.models.mirror import AgentStatus

    run_sync(api_client)
    enable_site(api_client, "dev-site")
    enable_site(api_client, "syd-site")
    agent = db.get(AgentStatus, "dev-site")
    now = agent.last_heartbeat_utc.replace(tzinfo=UTC) + timedelta(minutes=2)

    data = fs.freshness(db, allowed_site_ids=("dev-site", "syd-site"), now=now)
    states = {s["site_id"]: s["feed_state"] for s in data["sites"]}
    assert states == {"dev-site": "FRESH", "syd-site": "STALE"}  # syd-site has no agent heartbeat

    later = now + timedelta(minutes=30)
    assert fs.freshness(db, allowed_site_ids=("dev-site",), now=later)["sites"][0]["feed_state"] == "STALE"

    agent.pending_count = 5
    db.commit()
    assert fs.freshness(db, allowed_site_ids=("dev-site",), now=now)["sites"][0]["feed_state"] == "DELAYED"

    assert datetime.now(UTC)  # (sanity)
