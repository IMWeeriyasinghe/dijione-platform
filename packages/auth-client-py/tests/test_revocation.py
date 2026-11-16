"""Session revocation: snapshot states, outage and recovery, cold start, and the
FastAPI enforcement every API shares."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from auth_client_py import AuthClaims
from auth_client_py.fastapi_deps import fresh_if_sensitive, make_get_claims
from auth_client_py.revocation import FRESH, RESTRICTED, STALE, RevocationGuard, revocation_status, set_guard

SECRET = "unit-test-secret"
ALICE, BOB = 11, 12


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Feed:
    """A scriptable stand-in for platform-api's snapshot endpoint."""

    def __init__(self, users=None):
        self.users = users or {}
        self.etag = "v1"
        self.down = False
        self.calls = 0

    def set(self, users):
        self.users = users
        self.etag = f"v{self.calls}-{len(users)}-{sum(v for v, _ in users.values())}"

    def __call__(self, etag):
        self.calls += 1
        if self.down:
            raise ConnectionError("feed unreachable")
        if etag == self.etag:
            return 304, etag, None
        return 200, self.etag, dict(self.users)


def make_guard(feed, clock, **kw):
    return RevocationGuard(feed, clock=clock, **kw)


def token(user_id=ALICE, av=0, **extra):
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id), "iat": now, "exp": now + timedelta(hours=1), "iss": "dijione-dev-identity",
        "is_active": True, "full_name": "T", "email": "t@example.com", "platform_role": "PLATFORM_USER",
        "platform_permissions": [], "module_roles": {}, **extra,
    }
    if av is not None:
        payload["av"] = av
    return {"Authorization": "Bearer " + jwt.encode(payload, SECRET, algorithm="HS256")}


get_claims = make_get_claims(secret=SECRET)
app = FastAPI()


@app.get("/read")
def read(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"user": claims.user_id}


@app.post("/write")
def write(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"user": claims.user_id}


@app.post("/sensitive", dependencies=[Depends(fresh_if_sensitive("things.manage"))])
def sensitive(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"user": claims.user_id}


@app.post("/ordinary", dependencies=[Depends(fresh_if_sensitive("things.read"))])
def ordinary(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"user": claims.user_id}


client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_guard_afterwards():
    yield
    set_guard(None)


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def feed():
    return Feed({ALICE: (2, True), BOB: (1, False)})


def installed(feed, clock, **kw):
    guard = make_guard(feed, clock, **kw)
    set_guard(guard)
    return guard


# --- disabled ------------------------------------------------------------------


def test_nothing_changes_when_revocation_is_disabled():
    set_guard(None)
    assert client.get("/read", headers=token(av=0)).status_code == 200
    assert client.post("/sensitive", headers=token()).status_code == 200
    assert revocation_status() == {"enabled": False}


# --- verdicts ------------------------------------------------------------------


def test_stale_inactive_and_legacy_tokens_are_revoked_current_ones_are_not(feed, clock):
    guard = installed(feed, clock)
    assert guard.refresh_once() and guard.state() == FRESH
    assert client.get("/read", headers=token(ALICE, av=2)).status_code == 200  # current
    assert client.get("/read", headers=token(ALICE, av=3)).status_code == 200  # newer is fine
    old = client.get("/read", headers=token(ALICE, av=1))
    assert old.status_code == 401 and old.headers["x-auth-error"] == "session_revoked"
    assert client.get("/read", headers=token(ALICE, av=None)).status_code == 401  # legacy token = version 0
    assert client.get("/read", headers=token(BOB, av=99)).status_code == 401  # inactive, whatever its version
    assert client.get("/read", headers=token(77, av=0)).status_code == 200  # never changed: not listed


def test_supplier_and_external_sessions_are_not_user_sessions(feed, clock):
    installed(feed, clock).refresh_once()
    supplier = {"supplier": {"supplier_id": 5, "supplier_user_id": ALICE}}  # its id deliberately equals a user's
    assert client.get("/read", headers=token(ALICE, av=0, **supplier)).status_code == 200
    external = {"external": {"grant_id": 4}}
    assert client.get("/read", headers=token(ALICE, av=0, **external)).status_code == 200


# --- cold start ----------------------------------------------------------------


def test_a_replica_with_no_snapshot_is_restricted_not_open(feed, clock):
    feed.down = True
    guard = installed(feed, clock)
    guard.start()  # the bootstrap attempt fails
    guard.stop()
    assert guard.state() == RESTRICTED and guard.status()["snapshot_age_seconds"] is None
    assert client.get("/read", headers=token()).status_code == 200  # reads of non-sensitive data continue
    write = client.post("/write", headers=token())
    assert write.status_code == 503 and write.headers["x-auth-error"] == "revocation_restricted"
    assert client.post("/sensitive", headers=token()).status_code == 503
    assert client.post("/ordinary", headers=token()).status_code == 503  # a write, so refused


def test_a_normal_start_is_fresh_before_the_first_request(feed, clock):
    guard = installed(feed, clock)
    guard.start()
    guard.stop()
    assert guard.state() == FRESH
    assert client.post("/write", headers=token(ALICE, av=2)).status_code == 200


# --- outage: known revocations never lapse ---------------------------------------


def test_known_revocations_stay_enforced_through_every_stage_of_an_outage(feed, clock):
    guard = installed(feed, clock)
    guard.refresh_once()
    feed.down = True
    for elapsed, expected in ((60, FRESH), (400, STALE), (4000, RESTRICTED)):
        clock.now = 1000.0 + elapsed
        assert guard.refresh_once() is False
        assert guard.state() == expected
        assert client.get("/read", headers=token(ALICE, av=1)).status_code == 401  # still revoked
        assert client.get("/read", headers=token(BOB, av=5)).status_code == 401  # still inactive


def test_stale_blocks_sensitive_routes_only_and_restricted_blocks_all_writes(feed, clock):
    guard = installed(feed, clock)
    guard.refresh_once()
    feed.down = True
    clock.advance(600)  # STALE
    guard.refresh_once()
    assert guard.state() == STALE
    assert client.post("/write", headers=token(ALICE, av=2)).status_code == 200
    assert client.post("/ordinary", headers=token(ALICE, av=2)).status_code == 200
    stale = client.post("/sensitive", headers=token(ALICE, av=2))
    assert stale.status_code == 503 and stale.headers["x-auth-error"] == "revocation_stale"
    clock.advance(4000)  # RESTRICTED
    assert guard.state() == RESTRICTED
    assert client.get("/read", headers=token(ALICE, av=2)).status_code == 200
    assert client.post("/write", headers=token(ALICE, av=2)).status_code == 503
    assert client.post("/sensitive", headers=token(ALICE, av=2)).status_code == 503


def test_recovery_replaces_the_snapshot_and_restores_normal_service(feed, clock):
    guard = installed(feed, clock)
    guard.refresh_once()
    feed.down = True
    clock.advance(5000)
    guard.refresh_once()
    assert guard.state() == RESTRICTED
    feed.down = False
    feed.set({ALICE: (7, True)})  # BOB reactivated and untouched since; ALICE moved on
    assert guard.refresh_once() and guard.state() == FRESH
    assert client.post("/sensitive", headers=token(ALICE, av=7)).status_code == 200
    assert client.get("/read", headers=token(ALICE, av=2)).status_code == 401  # picked up while recovering
    assert client.get("/read", headers=token(BOB, av=0)).status_code == 200  # the whole snapshot was replaced


def test_an_unchanged_snapshot_refreshes_age_without_being_replaced(feed, clock):
    guard = installed(feed, clock)
    guard.refresh_once()
    before = guard._snapshot.users
    clock.advance(250)
    assert guard.refresh_once()  # 304
    assert guard._snapshot.users is before and guard.age_seconds() == 0


def test_unusable_responses_keep_the_previous_snapshot(clock):
    responses = iter([(200, "a", {ALICE: (2, True)}), (500, None, None), (200, "b", None)])
    guard = RevocationGuard(lambda etag: next(responses), clock=clock)
    assert guard.refresh_once()
    assert not guard.refresh_once() and not guard.refresh_once()
    assert guard.is_revoked(ALICE, 1) and not guard.is_revoked(ALICE, 2)


# --- several replicas -------------------------------------------------------------


def test_replicas_are_independent_and_each_converges_on_its_own_refresh(feed, clock):
    first, second = make_guard(feed, clock), make_guard(feed, clock)
    first.refresh_once()
    second.refresh_once()
    feed.set({ALICE: (5, True)})
    first.refresh_once()  # only one replica has refreshed so far
    assert first.is_revoked(ALICE, 2) and not second.is_revoked(ALICE, 2)
    second.refresh_once()
    assert second.is_revoked(ALICE, 2)


def test_a_restarted_replica_does_not_inherit_its_neighbours_snapshot(feed, clock):
    running = make_guard(feed, clock)
    running.refresh_once()
    feed.down = True
    restarted = make_guard(feed, clock)
    restarted.refresh_once()
    assert running.state() == FRESH and restarted.state() == RESTRICTED


def test_refresh_delay_backs_off_and_is_capped(feed, clock):
    guard = make_guard(feed, clock, refresh_seconds=30, max_backoff_seconds=60)
    healthy = guard._next_delay()
    assert 25 <= healthy <= 35
    feed.down = True
    for _ in range(8):
        guard.refresh_once()
    assert guard._next_delay() <= 60 * 1.15


# --- sensitivity ----------------------------------------------------------------------


@pytest.mark.parametrize("key", ["x.manage", "x.admin", "x.approve", "x.export", "onsite.identity.manage"])
def test_sensitive_permission_suffixes_require_fresh_revocation(key):
    assert fresh_if_sensitive(key).__name__ == "require_fresh_revocation"


@pytest.mark.parametrize("key", ["x.read", "x.write", "x.managed", "x.administer"])
def test_other_permissions_do_not(key):
    assert fresh_if_sensitive(key).__name__ == "_no_check"


def test_the_background_thread_keeps_refreshing_and_stops(feed):
    guard = RevocationGuard(feed, refresh_seconds=0.02, max_backoff_seconds=0.02)
    guard.start()
    import time

    deadline = time.time() + 2
    while feed.calls < 4 and time.time() < deadline:
        time.sleep(0.01)
    guard.stop()
    assert feed.calls >= 4
