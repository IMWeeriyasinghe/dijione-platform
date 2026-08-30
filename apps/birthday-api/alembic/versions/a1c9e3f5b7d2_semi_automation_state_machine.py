"""semi-automation future-state: retire the approval workflow status set,
add release/review/fulfilment provenance, exception typing, verify_by SLA,
default-cake flag, scan-run history, and structured order issues

Revision ID: a1c9e3f5b7d2
Revises: f8b3d1a4c206
Create Date: 2026-08-29 18:00:00.000000

Implements decision A ("verification is the approval" — no code-level
production data exists yet, so legacy statuses are remapped rather than
requiring a parallel-run migration): DRAFT/PLANNED/READY_FOR_APPROVAL/
APPROVED -> PENDING_VERIFICATION, REJECTED -> CANCELLED,
SUPPLIER_REVIEW -> CONFIRMED (the supplier had already acknowledged).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c9e3f5b7d2'
down_revision: Union[str, Sequence[str], None] = 'f8b3d1a4c206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_REMAP = {
    'DRAFT': 'PENDING_VERIFICATION',
    'PLANNED': 'PENDING_VERIFICATION',
    'READY_FOR_APPROVAL': 'PENDING_VERIFICATION',
    'APPROVED': 'PENDING_VERIFICATION',
    'REJECTED': 'CANCELLED',
    'SUPPLIER_REVIEW': 'CONFIRMED',
}


def upgrade() -> None:
    conn = op.get_bind()

    # 1. birthday_orders: new columns first, then remap legacy status
    #    values, then drop the columns the old approval workflow owned.
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('exception_reason', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('verify_by', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('released_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('released_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('review_confirmed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('review_confirmed_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('preparing_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('out_for_delivery_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))

    birthday_orders = sa.table('birthday_orders', sa.column('status', sa.String))
    for old_status, new_status in _STATUS_REMAP.items():
        conn.execute(
            birthday_orders.update()
            .where(birthday_orders.c.status == old_status)
            .values(status=new_status)
        )

    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by')
        batch_op.drop_column('is_overdue')
        batch_op.drop_column('has_delivery_issue')

    # 2. supplier_catalogue_items: default-cake flag (plan §31/§L).
    with op.batch_alter_table('supplier_catalogue_items', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table('supplier_catalogue_items', schema=None) as batch_op:
        batch_op.alter_column('is_default', server_default=None)

    # 3. birthday_detection_configs: semi-automation config (plan §U/§29).
    with op.batch_alter_table('birthday_detection_configs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('default_quantity', sa.Integer(), nullable=False, server_default='1')
        )
        batch_op.add_column(
            sa.Column('verify_buffer_days', sa.Integer(), nullable=False, server_default='2')
        )
        batch_op.add_column(
            sa.Column('acknowledgement_sla_hours', sa.Integer(), nullable=False, server_default='24')
        )
        batch_op.add_column(
            sa.Column('auto_release_enabled', sa.Boolean(), nullable=False, server_default=sa.true())
        )
    with op.batch_alter_table('birthday_detection_configs', schema=None) as batch_op:
        batch_op.alter_column('default_quantity', server_default=None)
        batch_op.alter_column('verify_buffer_days', server_default=None)
        batch_op.alter_column('acknowledgement_sla_hours', server_default=None)
        batch_op.alter_column('auto_release_enabled', server_default=None)

    # 4. scan_runs: detection-run audit history (plan §U) — replaces the
    #    previous 501 on GET /internal/scan-runs/{id}.
    op.create_table(
        'scan_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('trigger', sa.String(length=16), nullable=False, server_default='MANUAL'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('employees_scanned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('orders_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('orders_existing', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('exceptions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ineligible_skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors_json', sa.Text(), nullable=False, server_default='[]'),
    )
    op.create_index('ix_scan_runs_run_id', 'scan_runs', ['run_id'], unique=True)

    # 5. order_issues: structured supplier/internal problem reports (plan
    #    §U) — replaces the old free-text-only SUPPLIER_ISSUE event signal.
    op.create_table(
        'order_issues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('birthday_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('raised_by_type', sa.String(length=16), nullable=False),
        sa.Column('raised_by_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('detail', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='OPEN'),
        sa.Column('resolution_detail', sa.Text(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_order_issues_order_id', 'order_issues', ['order_id'])


def downgrade() -> None:
    op.drop_index('ix_order_issues_order_id', table_name='order_issues')
    op.drop_table('order_issues')
    op.drop_index('ix_scan_runs_run_id', table_name='scan_runs')
    op.drop_table('scan_runs')

    with op.batch_alter_table('birthday_detection_configs', schema=None) as batch_op:
        batch_op.drop_column('auto_release_enabled')
        batch_op.drop_column('acknowledgement_sla_hours')
        batch_op.drop_column('verify_buffer_days')
        batch_op.drop_column('default_quantity')

    with op.batch_alter_table('supplier_catalogue_items', schema=None) as batch_op:
        batch_op.drop_column('is_default')

    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('has_delivery_issue', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('is_overdue', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('approved_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))

    # Status values are not remapped back on downgrade — the legacy
    # approval-workflow statuses this migration retired are gone for good;
    # downgrading only restores the columns, not the historical statuses.

    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.drop_column('completed_at')
        batch_op.drop_column('delivered_at')
        batch_op.drop_column('out_for_delivery_at')
        batch_op.drop_column('preparing_at')
        batch_op.drop_column('accepted_at')
        batch_op.drop_column('review_confirmed_by')
        batch_op.drop_column('review_confirmed_at')
        batch_op.drop_column('released_by')
        batch_op.drop_column('released_at')
        batch_op.drop_column('verify_by')
        batch_op.drop_column('exception_reason')
