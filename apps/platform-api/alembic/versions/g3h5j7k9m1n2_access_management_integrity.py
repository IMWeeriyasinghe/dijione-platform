"""access management integrity: one assignment per principal and application; audit subject

Additive.

1. Unique constraints on user_module_roles(user_id, module_key) and
   group_module_roles(access_group_id, module_key). A second row for the same
   pair survives a revocation, so it must not be possible to create one.
2. audit_logs.subject_user_id (nullable, indexed): the user an administrative
   event is about, so one person's access history can be listed. Existing
   events are back-filled where the user is recorded in the event itself; the
   recorded content of no event is changed.

Preflight: the upgrade stops before changing anything if duplicate assignments
exist. They are never removed here; deciding which row is the intended one is a
separate, approved clean-up.

Revision ID: g3h5j7k9m1n2
Revises: f2a4b6c8d0e2
Create Date: 2026-11-16 00:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "g3h5j7k9m1n2"
down_revision: str | Sequence[str] | None = "f2a4b6c8d0e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNIQUE = (
    ("user_module_roles", "uq_user_module_roles_user_module", ("user_id", "module_key")),
    ("group_module_roles", "uq_group_module_roles_group_module", ("access_group_id", "module_key")),
)
_STATE_SUBJECT_ENTITIES = ("UserModuleRole", "UserGroupMembership")


def _duplicates(bind, table: str, columns: tuple[str, ...]) -> list[tuple]:
    cols = ", ".join(columns)
    return list(bind.execute(sa.text(f"SELECT {cols}, COUNT(*) FROM {table} GROUP BY {cols} HAVING COUNT(*) > 1")))


def _subject_from_states(*states: str | None) -> int | None:
    for state in states:
        try:
            value = json.loads(state or "").get("user_id")
        except (ValueError, AttributeError):
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def upgrade() -> None:
    bind = op.get_bind()

    problems = {table: rows for table, _name, columns in _UNIQUE if (rows := _duplicates(bind, table, columns))}
    if problems:
        detail = "; ".join(f"{table}: {len(rows)} duplicated pair(s) {rows[:5]}" for table, rows in problems.items())
        raise RuntimeError(
            "Duplicate access assignments exist, so the unique constraints cannot be added. "
            f"Nothing was changed. Resolve them with an approved clean-up first. {detail}"
        )

    # Safe to re-run, like the other platform migrations: each step is skipped when already applied.
    inspector = sa.inspect(bind)
    for table, name, columns in _UNIQUE:
        if name not in {u["name"] for u in inspector.get_unique_constraints(table)}:
            with op.batch_alter_table(table) as batch:
                batch.create_unique_constraint(name, list(columns))

    if "subject_user_id" not in {c["name"] for c in inspector.get_columns("audit_logs")}:
        column = sa.Column("subject_user_id", sa.Integer(), nullable=True)
        if bind.dialect.name == "sqlite":
            # SQLite rebuilds the table. Keeping event_id last there keeps the earlier
            # event_id migration re-runnable over an upgraded database.
            with op.batch_alter_table("audit_logs", recreate="always") as batch:
                batch.add_column(column, insert_before="event_id")
        else:
            op.add_column("audit_logs", column)
        op.create_index("ix_audit_logs_subject_user_id", "audit_logs", ["subject_user_id"])

    bind.execute(
        sa.text("UPDATE audit_logs SET subject_user_id = entity_id WHERE entity_type = 'User' AND subject_user_id IS NULL")
    )
    known_users = {row[0] for row in bind.execute(sa.text("SELECT id FROM users"))}
    rows = bind.execute(
        sa.text(
            "SELECT id, previous_state, new_state FROM audit_logs"
            " WHERE entity_type IN :types AND subject_user_id IS NULL"
        ).bindparams(
            sa.bindparam("types", expanding=True)
        ),
        {"types": list(_STATE_SUBJECT_ENTITIES)},
    ).all()
    for audit_id, previous_state, new_state in rows:
        subject = _subject_from_states(new_state, previous_state)
        if subject in known_users:
            bind.execute(
                sa.text("UPDATE audit_logs SET subject_user_id = :subject WHERE id = :id"),
                {"subject": subject, "id": audit_id},
            )


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_index("ix_audit_logs_subject_user_id")
        batch.drop_column("subject_user_id")
    for table, name, _columns in reversed(_UNIQUE):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="unique")
