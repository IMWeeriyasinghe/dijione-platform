"""talent-api owns no User/UserModuleRole table, so tests can't dev-login
against a running platform-api — they mint the same signed claims Platform
Core would issue, locally, with the shared HS256 secret, and assert against
that. This exercises exactly what talent-api's ``get_talent_scope`` actually
decodes, without needing a second live service for the test suite to pass.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Honour a pre-set DATABASE_URL (the `postgres` CI workflow points this
# at a real Postgres 16); fall back to a local SQLite file otherwise.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_talent.db")
os.environ["JWT_DEV_SECRET"] = "test-only-secret"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"
os.environ["INTEGRATIONS_MODE"] = "mock"
# Deliberately unroutable — talent-api's audit/notification writes to
# Platform Core must be best-effort (CR §21, §27); pointing tests at a
# reserved port makes that fallback deterministic and fast (immediate
# connection refusal) instead of depending on whether something happens to
# be listening on the real default port.
os.environ["PLATFORM_API_URL"] = "http://127.0.0.1:1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.client import Client  # noqa: E402

TALENT_PERMISSIONS_BY_ROLE = {
    # talent.requests.create and talent.candidates.manage are retired — no
    # role is granted either (DijiTalentFlow real-data completion,
    # 2026-09-01/02; see app/core/permissions.py in platform-api, the
    # authoritative copy this list mirrors).
    "TALENT_CLIENT": [
        "talent.dashboard.read_own", "talent.requests.read_own",
        "talent.candidates.read_client_safe", "talent.interviews.read_own",
        "talent.messages.read_own", "talent.messages.create",
        "talent.documents.read_own", "talent.documents.create",
    ],
    "TA_MEMBER": [
        "talent.workspace.staff", "talent.dashboard.read", "talent.clients.read",
        "talent.requests.read", "talent.requests.update", "talent.candidates.read",
        "talent.applications.read", "talent.applications.create",
        "talent.applications.update", "talent.interviews.read", "talent.interviews.manage",
        "talent.messages.read", "talent.messages.create", "talent.documents.read",
        "talent.documents.create",
    ],
    "CUSTOMER_SUCCESS": [
        "talent.workspace.staff", "talent.dashboard.read", "talent.clients.read",
        "talent.requests.read", "talent.requests.update", "talent.candidates.read",
        "talent.applications.read", "talent.applications.create",
        "talent.applications.update", "talent.interviews.read", "talent.interviews.manage",
        "talent.messages.read", "talent.messages.create", "talent.documents.read",
        "talent.documents.create", "talent.requests.review",
    ],
}


def issue_token(
    user_id: int, *, full_name: str = "", role: str | None = None,
    client_id: int | None = None, client_ids: list[int] | None = None,
    client_public_id: str | None = None, client_public_ids: list[str] | None = None,
) -> str:
    now = datetime.now(UTC)
    module_roles = {}
    if role is not None:
        module_roles["talent-flow"] = {
            "role": role, "client_id": client_id, "client_ids": client_ids,
            "client_public_id": client_public_id, "client_public_ids": client_public_ids,
            "permissions": TALENT_PERMISSIONS_BY_ROLE[role],
        }
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=60),
        "iss": "dijione-dev-identity",
        "is_active": True,
        "full_name": full_name,
        "email": f"user{user_id}@example.com",
        "platform_role": "PLATFORM_USER",
        "platform_permissions": [],
        "module_roles": module_roles,
    }
    return jwt.encode(payload, os.environ["JWT_DEV_SECRET"], algorithm="HS256")


def headers_for(user_id: int, **kwargs) -> dict:
    return {"Authorization": f"Bearer {issue_token(user_id, **kwargs)}"}


def make_magic_link_grant(
    db,
    client,
    *,
    issued_by_user_id: int = 103,
    expires_delta: timedelta | None = None,
    revoked: bool = False,
    contact_name: str = "External Reviewer",
    contact_email: str = "reviewer@client.example",
):
    """Create a real MagicLinkGrant row (the same architecture the redeem
    path and get_talent_external_scope re-validate) and return
    ``(grant, raw_token)``. Never fabricates client business data — only
    the grant/session plumbing."""
    from app.models.magic_link_grant import MagicLinkGrant
    from app.services.magic_link_service import generate_raw_token

    raw, token_hash, token_prefix = generate_raw_token()
    now = datetime.now(UTC)
    grant = MagicLinkGrant(
        public_id=f"mlg-test-{token_prefix}",
        client_id=client.id,
        contact_name=contact_name,
        contact_email=contact_email,
        token_hash=token_hash,
        token_prefix=token_prefix,
        issued_by_user_id=issued_by_user_id,
        issued_at=now,
        expires_at=now + (expires_delta if expires_delta is not None else timedelta(days=14)),
        revoked_at=now if revoked else None,
        revoked_by_user_id=issued_by_user_id if revoked else None,
    )
    db.add(grant)
    db.commit()
    return grant, raw


def external_headers_for(db, client, **kwargs) -> dict:
    """Bearer header for a magic-link external session scoped to ``client``.
    Mints the session JWT exactly the way the redeem endpoint does."""
    from app.services.magic_link_service import MagicLinkService

    grant, _ = make_magic_link_grant(db, client, **kwargs)
    token, _ = MagicLinkService(db).mint_session_jwt(grant)
    return {"Authorization": f"Bearer {token}"}


def recruitment_posting_dto(
    external_id: str, *, title: str = "Role", dtc_status: str = "NO_TAG",
    dtc_client_name: str | None = None, dtc_raw_tag: str | None = None,
    dtc_raw_tags: list[str] | None = None,
    state: str = "published", location: str = "Sri Lanka", archived: bool = False,
) -> dict:
    """Shape of one item from RecruitmentSourceClient.list_postings()."""
    raw_tags = dtc_raw_tags if dtc_raw_tags is not None else ([dtc_raw_tag] if dtc_raw_tag else [])
    return {
        "provider": "LEVER", "external_id": external_id, "title": title, "state": state,
        "team": "", "department": "", "location": location, "confidentiality": "",
        "tags": list(raw_tags), "archived": archived,
        "dtc_tag": {
            "status": dtc_status, "client_name": dtc_client_name,
            "raw_tag": dtc_raw_tag, "raw_tags": list(raw_tags),
        },
        "lever_created_at": None, "lever_updated_at": None, "synced_at": None,
    }


def recruitment_candidacy_dto(
    external_id: str, *, posting_external_id: str, candidate_external_id: str,
    candidate_name: str = "Jane Candidate", candidate_email: str = "",
    candidate_headline: str = "", current_stage: str = "SOURCING", status: str = "ACTIVE",
    lever_archive_reason: str | None = None, synced_at: str | None = None,
) -> dict:
    """Shape of one item from RecruitmentSourceClient.list_candidacies()."""
    return {
        "provider": "LEVER", "external_id": external_id,
        "posting_external_id": posting_external_id,
        "candidate_external_id": candidate_external_id,
        "candidate_name": candidate_name, "candidate_email": candidate_email,
        "candidate_headline": candidate_headline, "current_stage": current_stage,
        "status": status, "lever_archive_reason": lever_archive_reason,
        "synced_at": synced_at,
    }


class FakeRecruitmentClient:
    """Stand-in for auth_client_py.RecruitmentSourceClient. ``down=True``
    makes every method raise httpx.HTTPError (source-outage simulation);
    ``candidacies_down=True`` fails only ``list_candidacies`` — used to
    prove the promotion reconciler degrades to "postings only" rather than
    aborting when candidacies specifically are unavailable."""

    def __init__(
        self,
        postings: list[dict] | None = None,
        *,
        candidacies: list[dict] | None = None,
        down: bool = False,
        candidacies_down: bool = False,
    ):
        self._postings = postings or []
        self._candidacies = candidacies or []
        self.down = down
        self.candidacies_down = candidacies_down
        self.sync_calls: list[dict] = []

    def _guard(self):
        if self.down:
            import httpx

            raise httpx.ConnectError("recruitment-api unreachable")

    def list_postings(self, *, include_archived: bool = True) -> list[dict]:
        self._guard()
        return list(self._postings)

    def list_candidacies(
        self, *, posting_external_id: str | None = None, limit: int = 200
    ) -> list[dict]:
        self._guard()
        if self.candidacies_down:
            import httpx

            raise httpx.ConnectError("recruitment-api candidacies unreachable")
        rows = self._candidacies
        if posting_external_id is not None:
            rows = [r for r in rows if r.get("posting_external_id") == posting_external_id]
        return list(rows[:limit])

    def get_freshness(self) -> dict:
        self._guard()
        return {"provider": "LEVER", "last_successful_sync_at": "2026-09-01T00:00:00+00:00", "latest_run": None}

    def request_sync(self, *, requested_by_user_id=None, requested_by_application="talent-flow") -> dict:
        self._guard()
        self.sync_calls.append({"user": requested_by_user_id})
        return {"run_id": "run-fake", "status": "QUEUED", "started": True, "message": "Sync started"}


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def platform_calls(monkeypatch):
    """talent-api records audit events/notifications through Platform
    Core's HTTP API (AuditService/NotificationService wrap
    ``auth_client_py.PlatformClient``) rather than a local table now, so
    tests assert against *what would have been sent*, not a local
    AuditLog/Notification row — patches the PlatformClient methods those
    services call and records every invocation.

    Autouse: every test gets this fast, in-memory stand-in by default (no
    test should pay for a real, possibly slow, connection attempt to a
    dead port just because it happened to create a talent request).
    Dedicated resilience tests that want the *real* best-effort network
    fallback undo the patch explicitly via ``monkeypatch.undo()`` or by
    constructing a ``PlatformClient`` directly.
    """
    from auth_client_py import PlatformClient

    calls = {"audit_events": [], "notifications": [], "broadcasts": []}

    def _record_audit_event(self, **kwargs):
        calls["audit_events"].append(kwargs)
        return True

    def _notify_user(self, **kwargs):
        calls["notifications"].append(kwargs)
        return True

    def _broadcast_notification(self, **kwargs):
        calls["broadcasts"].append(kwargs)
        return True

    monkeypatch.setattr(PlatformClient, "record_audit_event", _record_audit_event)
    monkeypatch.setattr(PlatformClient, "notify_user", _notify_user)
    monkeypatch.setattr(PlatformClient, "broadcast_notification", _broadcast_notification)
    return calls


@pytest.fixture()
def two_tenant_world(db):
    """Two clients, one client-user each, one TA member, one CS user —
    fixed ids chosen simply to be distinct from client ids, mirroring the
    pre-split fixture's shape."""
    abc = Client(
        name="ABC Company", platform_client_id="cli-abc-company",
        industry="Financial Services", status="ACTIVE",
    )
    xyz = Client(
        name="XYZ Company", platform_client_id="cli-xyz-company",
        industry="Retail", status="ACTIVE",
    )
    db.add_all([abc, xyz])
    db.commit()

    return {
        "abc": abc,
        "xyz": xyz,
        "abc_user_id": 101,
        "xyz_user_id": 102,
        "ta_user_id": 103,
        "cs_user_id": 104,
        "abc_headers": headers_for(101, full_name="ABC Client User", role="TALENT_CLIENT", client_id=abc.id),
        "xyz_headers": headers_for(102, full_name="XYZ Client User", role="TALENT_CLIENT", client_id=xyz.id),
        "ta_headers": headers_for(103, full_name="TA User", role="TA_MEMBER"),
        "cs_headers": headers_for(104, full_name="CS User", role="CUSTOMER_SUCCESS"),
    }
