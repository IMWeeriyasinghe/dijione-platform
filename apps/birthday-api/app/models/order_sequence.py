from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OrderSequence(TimestampMixin, Base):
    """Dedicated per-year counter table for order-reference generation,
    avoiding a COUNT+1 race under concurrent/retried scan runs."""

    __tablename__ = "order_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    next_seq: Mapped[int] = mapped_column(Integer, default=1)
