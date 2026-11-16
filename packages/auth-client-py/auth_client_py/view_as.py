"""Read-only enforcement for View-as sessions.

A View-as token is signed for the employee being viewed, so every application authorizes the
request as that employee. What makes the session read-only is enforced here, for every API that
verifies user tokens, in three independent layers:

1. ``fastapi_deps`` admits a View-as request only to a GET route the service's route policy marks
   READ. Everything else (changes, own-data actions, sensitive reads, exports, unlisted routes,
   and every route of a service with no policy) is refused with 403.
2. For a request that is admitted, a context flag is set. A SQLAlchemy listener then refuses any
   flush, INSERT/UPDATE/DELETE or DDL attempted in that request, even if a handler marked READ
   were to write by mistake.
3. The shared ``PlatformClient`` sends no audit events or notifications while the flag is set.

Every refused attempt is recorded in the audit log (best effort, off the request path).
"""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from contextvars import ContextVar

from fastapi import HTTPException, status

logger = logging.getLogger("dijione.view_as")

READ_ONLY_DETAIL = "This is a read-only View-as session: changes are not allowed"
BLOCKED_HEADER = {"X-Auth-Error": "view_as_read_only"}

_active: ContextVar[bool] = ContextVar("dijione_view_as_active", default=False)
_guard_installed = False
_LEADING_NOISE = re.compile(r"\A(?:\s+|/\*.*?\*/|--[^\n]*(?:\n|\Z))*", re.DOTALL)
_WRITE_VERB = (
    r"(?:insert|update|delete|merge|replace|create|alter|drop|truncate|grant|revoke"
    r"|call|exec|execute|do|copy|vacuum|analyze|reindex)"
)
_STARTS_WITH_WRITE = re.compile(rf"\A{_WRITE_VERB}\b", re.IGNORECASE)
_WRITE_INSIDE_WITH = re.compile(r"\b(?:insert|update|delete|merge)\b", re.IGNORECASE)
# Reports of refusals are sent from short-lived threads; never more than this many at once.
_audit_slots = threading.BoundedSemaphore(8)


def is_write_sql(statement: str) -> bool:
    """True for SQL that changes data or schema: a statement that starts with a write verb (after any
    leading whitespace or comments), or a ``WITH`` statement containing INSERT/UPDATE/DELETE/MERGE."""
    body = statement[_LEADING_NOISE.match(statement).end():]
    if _STARTS_WITH_WRITE.match(body):
        return True
    return body[:4].lower() == "with" and bool(_WRITE_INSIDE_WITH.search(body))


class ViewAsWriteBlocked(HTTPException):
    def __init__(self) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, READ_ONLY_DETAIL, headers=BLOCKED_HEADER)


def view_as_active() -> bool:
    return _active.get()


def mark_view_as_active() -> None:
    """Called once a View-as request has been admitted. The flag lives in the request's context."""
    _active.set(True)


def install_read_only_guard() -> None:
    """Refuse database writes made while a View-as request is being served. Idempotent; a no-op
    where SQLAlchemy is not installed."""
    global _guard_installed
    if _guard_installed:
        return
    try:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        from sqlalchemy.orm import Session
        from sqlalchemy.sql import Delete, Insert, Update
        from sqlalchemy.sql.elements import TextClause
    except ImportError:  # pragma: no cover - every service using this has SQLAlchemy
        return

    @event.listens_for(Session, "before_flush")
    def _refuse_flush(session, _ctx, _instances) -> None:
        if _active.get() and (session.new or session.deleted or any(session.is_modified(o) for o in session.dirty)):
            logger.warning("refused a database write during a read-only View-as session")
            raise ViewAsWriteBlocked()

    @event.listens_for(Session, "do_orm_execute")
    def _refuse_statement(state) -> None:
        if not _active.get():
            return
        statement = state.statement
        if isinstance(statement, (Insert, Update, Delete)) or (
            isinstance(statement, TextClause) and is_write_sql(statement.text)
        ):
            logger.warning("refused a database statement during a read-only View-as session")
            raise ViewAsWriteBlocked()

    # The last line of defence sits at the cursor, so it also stops writes that bypass the Session:
    # ``Session.connection().execute``, an Engine or Connection used directly, comment-prefixed SQL,
    # and ``WITH ... INSERT``.
    @event.listens_for(Engine, "before_cursor_execute")
    def _refuse_cursor_write(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        if _active.get() and is_write_sql(statement):
            logger.warning("refused a database statement at the cursor during a read-only View-as session")
            raise ViewAsWriteBlocked()

    _guard_installed = True


def record_blocked_attempt(claims, method: str, path: str) -> None:
    """Audit a refused View-as request: who was looking, as whom, and what was attempted. Runs in a
    background thread (a fresh context, so the View-as flag does not suppress it) and never delays or
    fails the request."""
    view_as = claims.view_as
    base, secret = os.environ.get("PLATFORM_API_URL", ""), os.environ.get("INTERNAL_SERVICE_SECRET", "")
    logger.warning(
        "View-as request refused: session %s, administrator %s as employee %s, %s %s",
        view_as.session_id, view_as.actor_id, claims.user_id, method, path,
    )
    if not base or not secret:
        return
    if not _audit_slots.acquire(blocking=False):  # a burst of refusals must not become a thread flood
        logger.warning("View-as refusal not sent to the audit log: too many reports in flight")
        return

    def send() -> None:
        try:
            from auth_client_py.platform_client import PlatformClient

            PlatformClient(base, secret, timeout=3.0, caller="view-as-guard").record_audit_event(
                actor_id=view_as.actor_id or None,
                action="view_as.blocked",
                entity_type="User",
                entity_id=claims.user_id,
                subject_user_id=claims.user_id,
                new_state={"session_id": view_as.session_id, "method": method, "path": path},
                metadata={"event": str(uuid.uuid4())},
            )
        finally:
            _audit_slots.release()

    threading.Thread(target=send, name="view-as-audit", daemon=True).start()
