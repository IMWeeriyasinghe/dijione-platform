"""View-as enforcement in the shared authorization layer: a View-as request reaches only READ routes,
never writes the database, and every refusal is audited."""

import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import Column, Integer, String, create_engine, insert, select, text
from sqlalchemy.orm import DeclarativeBase, Session

from auth_client_py import AuthClaims, PlatformClient, ViewAsClaims
from auth_client_py import revocation as rev
from auth_client_py import view_as as va
from auth_client_py.fastapi_deps import make_get_claims
from auth_client_py.revocation import RevocationGuard, register_route_policy, set_guard

SECRET = "view-as-test-secret"


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    body = Column(String)


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=__import__("sqlalchemy").pool.StaticPool)
Base.metadata.create_all(engine)

get_claims = make_get_claims(secret=SECRET)
app = FastAPI()


@app.get("/read")
def read(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"user": claims.user_id, "view_as": claims.view_as is not None}


@app.get("/read-that-writes")  # a mistake the database guard must still catch
def read_that_writes(claims: AuthClaims = Depends(get_claims)) -> dict:
    with Session(engine) as s:
        s.add(Note(body="oops"))
        s.commit()
    return {"ok": True}


@app.get("/read-that-executes")
def read_that_executes(claims: AuthClaims = Depends(get_claims)) -> dict:
    with Session(engine) as s:
        s.execute(insert(Note).values(body="core"))
        s.commit()
    return {"ok": True}


@app.get("/read-that-runs-sql")
def read_that_runs_sql(claims: AuthClaims = Depends(get_claims)) -> dict:
    with Session(engine) as s:
        s.execute(text("UPDATE notes SET body = 'x'"))
        s.commit()
    return {"ok": True}


@app.get("/read-that-uses-the-connection")
def read_that_uses_the_connection(claims: AuthClaims = Depends(get_claims)) -> dict:
    with Session(engine) as s:
        s.connection().execute(insert(Note).values(body="via connection"))
        s.commit()
    return {"ok": True}


@app.get("/read-that-comments-first")
def read_that_comments_first(claims: AuthClaims = Depends(get_claims)) -> dict:
    with engine.begin() as c:
        c.exec_driver_sql("/* looks harmless */ -- really\nINSERT INTO notes (body) VALUES ('sneaky')")
    return {"ok": True}


@app.get("/read-that-uses-a-cte")
def read_that_uses_a_cte(claims: AuthClaims = Depends(get_claims)) -> dict:
    with engine.begin() as c:
        c.exec_driver_sql("WITH x AS (SELECT 1 AS v) INSERT INTO notes (body) SELECT 'cte' FROM x")
    return {"ok": True}


@app.get("/read-that-selects-for-update")
def read_that_selects_for_update(claims: AuthClaims = Depends(get_claims)) -> dict:
    with engine.begin() as c:
        rows = c.exec_driver_sql("SELECT body FROM notes WHERE body = 'update' OR body LIKE '%delete%'").all()
    return {"rows": len(rows)}


@app.get("/read-that-selects")
def read_that_selects(claims: AuthClaims = Depends(get_claims)) -> dict:
    with Session(engine) as s:
        return {"count": len(s.execute(select(Note)).all()), "raw": s.execute(text("SELECT 1")).scalar()}


@app.get("/read-that-notifies")
def read_that_notifies(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"sent": PlatformClient("http://platform-api", "secret").notify_user(user_id=1, type="x", title="t")}


@app.post("/write")
def write(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"ok": True}


@app.post("/own")
def own(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"ok": True}


@app.get("/export")
def export(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"ok": True}


@app.get("/unlisted")
def unlisted(claims: AuthClaims = Depends(get_claims)) -> dict:
    return {"ok": True}


POLICY = {
    "GET /read": "READ", "GET /read-that-writes": "READ", "GET /read-that-executes": "READ",
    "GET /read-that-runs-sql": "READ", "GET /read-that-selects": "READ", "GET /read-that-notifies": "READ",
    "GET /read-that-uses-the-connection": "READ", "GET /read-that-comments-first": "READ",
    "GET /read-that-uses-a-cte": "READ", "GET /read-that-selects-for-update": "READ",
    "POST /write": "WRITE", "POST /own": "OWN", "GET /export": "SENSITIVE",
}
client = TestClient(app)
EMPLOYEE, ADMIN = 21, 9


def token(*, view_as=True, actor_type="view_as", **extra):
    now = datetime.now(UTC)
    payload = {
        "sub": str(EMPLOYEE), "iat": now, "exp": now + timedelta(minutes=30), "iss": "dijione-dev-identity",
        "is_active": True, "full_name": "Emp", "email": "emp@example.com", "platform_role": "PLATFORM_USER",
        "platform_permissions": [], "module_roles": {}, "av": 0, "actor_type": actor_type, **extra,
    }
    if view_as:
        payload["view_as"] = {"session_id": "S-1", "actor_id": ADMIN, "actor_name": "Admin", "actor_av": 0}
    return {"Authorization": "Bearer " + jwt.encode(payload, SECRET, algorithm="HS256")}


@pytest.fixture(autouse=True)
def _policy_and_clean_state():
    register_route_policy(POLICY)
    with engine.begin() as c:
        c.execute(text("DELETE FROM notes"))
    yield
    set_guard(None)
    rev._route_policy = None


def notes():
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM notes")).scalar_one()


# --- the route gate ------------------------------------------------------------------------------


def test_a_view_as_session_reaches_read_routes_as_the_employee():
    resp = client.get("/read", headers=token())
    assert resp.status_code == 200 and resp.json() == {"user": EMPLOYEE, "view_as": True}


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/write"), ("post", "/own"), ("get", "/export"), ("get", "/unlisted"), ("delete", "/write"),
     ("put", "/write"), ("patch", "/write")],
)
def test_everything_except_a_read_route_is_refused(method, path):
    resp = getattr(client, method)(path, headers=token())
    assert resp.status_code in (403, 405) and (resp.status_code == 405 or resp.headers["x-auth-error"] == "view_as_read_only")


def test_a_staff_session_is_unaffected():
    assert client.post("/write", headers=token(view_as=False, actor_type="staff")).status_code == 200


def test_a_token_that_says_view_as_but_omits_the_detail_is_still_read_only():
    resp = client.post("/write", headers=token(view_as=False, actor_type="view_as"))
    assert resp.status_code == 403 and resp.headers["x-auth-error"] == "view_as_read_only"
    assert client.get("/read", headers=token(view_as=False, actor_type="view_as")).status_code == 200


def test_a_service_with_no_policy_refuses_every_view_as_request():
    rev._route_policy = None
    assert client.get("/read", headers=token()).status_code == 403


def test_the_gate_does_not_depend_on_revocation_being_enabled():
    set_guard(None)  # revocation off
    assert client.post("/write", headers=token()).status_code == 403


def test_head_is_treated_as_get_and_nothing_else_is():
    assert client.head("/read", headers=token()).status_code in (200, 405)


def test_the_view_as_flag_does_not_leak_into_the_next_request():
    assert client.get("/read", headers=token()).status_code == 200
    assert client.post("/write", headers=token(view_as=False, actor_type="staff")).status_code == 200
    with Session(engine) as s:
        s.add(Note(body="outside any request"))
        s.commit()
    assert notes() == 1


# --- the database backstop --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/read-that-writes", "/read-that-executes", "/read-that-runs-sql", "/read-that-uses-the-connection",
     "/read-that-comments-first", "/read-that-uses-a-cte"],
)
def test_a_read_route_that_tries_to_write_is_stopped_and_nothing_is_saved(path):
    with engine.begin() as c:
        c.execute(text("INSERT INTO notes (body) VALUES ('keep')"))
    resp = client.get(path, headers=token())
    assert resp.status_code == 403 and resp.headers["x-auth-error"] == "view_as_read_only"
    with engine.connect() as c:
        assert [r[0] for r in c.execute(text("SELECT body FROM notes"))] == ["keep"]


@pytest.mark.parametrize(
    ("sql", "is_write"),
    [
        ("SELECT * FROM notes", False),
        ("  select body from notes where body = 'update'", False),
        ("SELECT * FROM notes FOR UPDATE", False),
        ("WITH x AS (SELECT 1) SELECT * FROM x", False),
        ("PRAGMA table_info(notes)", False),
        ("SAVEPOINT sa_1", False),
        ("INSERT INTO notes (body) VALUES ('x')", True),
        ("  update notes set body = 'x'", True),
        ("DELETE FROM notes", True),
        ("/* c */ INSERT INTO notes VALUES (1)", True),
        ("-- c\nUPDATE notes SET body = 'x'", True),
        ("WITH x AS (SELECT 1) INSERT INTO notes SELECT * FROM x", True),
        ("WITH d AS (DELETE FROM notes RETURNING *) SELECT * FROM d", True),
        ("DROP TABLE notes", True),
        ("CREATE TABLE t (a int)", True),
        ("TRUNCATE notes", True),
        ("CALL do_something()", True),
    ],
)
def test_what_counts_as_a_database_write(sql, is_write):
    assert va.is_write_sql(sql) is is_write


def test_reads_that_mention_write_words_in_their_data_are_not_blocked():
    with engine.begin() as c:
        c.execute(text("INSERT INTO notes (body) VALUES ('update'), ('delete me')"))
    resp = client.get("/read-that-selects-for-update", headers=token())
    assert resp.status_code == 200 and resp.json() == {"rows": 2}


def test_reports_of_refusals_are_bounded_not_a_thread_per_request(monkeypatch):
    started = []
    monkeypatch.setenv("PLATFORM_API_URL", "http://platform-api")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s")
    release = threading.Event()

    def slow(self, **kwargs):
        started.append(1)
        release.wait(5)
        return True

    monkeypatch.setattr(PlatformClient, "record_audit_event", slow)
    for _ in range(40):
        assert client.post("/write", headers=token()).status_code == 403
    release.set()
    deadline = time.time() + 3
    while len(started) < 8 and time.time() < deadline:
        time.sleep(0.01)
    assert 1 <= len(started) <= 8  # excess reports are dropped (and logged), the requests are still refused


def test_a_revoked_view_as_session_is_refused_without_being_reported(monkeypatch):
    sent = []
    monkeypatch.setenv("PLATFORM_API_URL", "http://platform-api")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s")
    monkeypatch.setattr(PlatformClient, "record_audit_event", lambda self, **kw: sent.append(kw) or True)
    guard = RevocationGuard(lambda etag: (200, "e", {EMPLOYEE: (9, True)}))
    guard.refresh_once()
    set_guard(guard)
    assert client.post("/write", headers=token()).status_code == 401  # revoked first
    assert sent == []


def test_reads_are_not_affected_by_the_database_guard():
    assert client.get("/read-that-selects", headers=token()).json() == {"count": 0, "raw": 1}


def test_the_same_routes_write_normally_for_a_staff_session():
    assert client.get("/read-that-writes", headers=token(view_as=False, actor_type="staff")).status_code == 200
    assert notes() == 1


def test_no_notification_or_audit_leaves_during_a_view_as_request(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("an HTTP call was made")

    monkeypatch.setattr(httpx, "request", forbidden)
    assert client.get("/read-that-notifies", headers=token()).json() == {"sent": False}


# --- audit of refusals --------------------------------------------------------------------------------


def test_every_refusal_is_audited_with_who_as_whom_and_what(monkeypatch):
    sent, done = [], threading.Event()
    monkeypatch.setenv("PLATFORM_API_URL", "http://platform-api")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s")

    def capture(self, **kwargs):
        sent.append(kwargs)
        done.set()
        return True

    monkeypatch.setattr(PlatformClient, "record_audit_event", capture)
    assert client.post("/write", headers=token()).status_code == 403
    assert done.wait(3)
    event = sent[0]
    assert event["action"] == "view_as.blocked" and event["actor_id"] == ADMIN and event["subject_user_id"] == EMPLOYEE
    assert event["new_state"] == {"session_id": "S-1", "method": "POST", "path": "/write"}


def test_an_allowed_read_is_not_a_refusal_and_is_not_audited(monkeypatch):
    sent = []
    monkeypatch.setenv("PLATFORM_API_URL", "http://platform-api")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s")
    monkeypatch.setattr(PlatformClient, "record_audit_event", lambda self, **kw: sent.append(kw) or True)
    assert client.get("/read", headers=token()).status_code == 200
    assert sent == []


# --- the session ends with the people involved -------------------------------------------------------------


def _guard(users):
    guard = RevocationGuard(lambda etag: (200, "e", users))
    guard.refresh_once()
    set_guard(guard)


def test_a_view_as_session_is_revoked_when_the_employees_access_changes():
    _guard({EMPLOYEE: (5, True)})
    resp = client.get("/read", headers=token())  # av 0 < 5
    assert resp.status_code == 401 and resp.headers["x-auth-error"] == "session_revoked"


def test_a_view_as_session_is_revoked_when_the_administrator_is_deactivated_or_changed():
    _guard({ADMIN: (0, False)})
    assert client.get("/read", headers=token()).status_code == 401
    _guard({ADMIN: (3, True)})  # administrator's own access changed since the session began (actor_av 0)
    assert client.get("/read", headers=token()).status_code == 401


def test_claims_expose_the_view_as_facts():
    from auth_client_py.claims import decode_claims

    raw = token()["Authorization"].split()[1]
    claims = decode_claims(raw, secret=SECRET)
    assert claims.view_as == ViewAsClaims(session_id="S-1", actor_id=ADMIN, actor_name="Admin", actor_av=0)
    assert va.view_as_active() is False
