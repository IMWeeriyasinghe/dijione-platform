"""Module capability: supports_client_scope

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-11-02

Generic registry metadata telling Admin Center whether a module's
authorization reads client (customer) scope. Defaults to true so every
existing module keeps its current Client Scope behaviour; Diji On-site
(``key='onsite'``) does not read client scope and is set to false.
"""

import sqlalchemy as sa

from alembic import op

revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("application_modules") as batch:
        batch.add_column(sa.Column("supports_client_scope", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE application_modules SET supports_client_scope = false WHERE key = 'onsite'")


def downgrade() -> None:
    with op.batch_alter_table("application_modules") as batch:
        batch.drop_column("supports_client_scope")
