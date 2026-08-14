"""Generates human-readable, per-year-sequential order references.

Uses the dedicated ``OrderSequence`` counter table (one row per year) rather
than COUNT(*)+1 against ``birthday_orders``, which would race under
concurrent/retried scan runs. SQLite has no cross-process row-level locking
like Postgres' ``SELECT ... FOR UPDATE``, so instead we rely on the
surrounding request's transaction plus a retry loop on IntegrityError from
the ``year`` unique constraint — safe under both SQLite (single-writer,
serialized) and Postgres (real row locks once migrated), matching the
retry-on-conflict idiom used by ``create_or_get_order``.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order_sequence import OrderSequence


def next_order_reference(db: Session, employee_id: str, year: int) -> str:
    seq = _next_seq_for_year(db, year)
    return f"BDAY-EMP{employee_id}-{year}-{seq:05d}"


def _next_seq_for_year(db: Session, year: int, _retries: int = 3) -> int:
    query = db.query(OrderSequence).filter(OrderSequence.year == year)
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        # Real row lock on Postgres/etc — SQLite has no comparable
        # cross-process locking, so the retry-on-IntegrityError below
        # carries the safety burden there instead.
        query = query.with_for_update()
    row = query.first()

    if row is None:
        row = OrderSequence(year=year, next_seq=1)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            if _retries <= 0:
                raise
            return _next_seq_for_year(db, year, _retries - 1)

    seq = row.next_seq
    row.next_seq = seq + 1
    db.flush()
    return seq
