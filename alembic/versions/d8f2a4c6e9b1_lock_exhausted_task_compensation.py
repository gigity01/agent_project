"""lock exhausted task compensation

Revision ID: d8f2a4c6e9b1
Revises: c2d4e6f8a0b1
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8f2a4c6e9b1"
down_revision: Union[str, Sequence[str], None] = "c2d4e6f8a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_executions",
        sa.Column(
            "compensation_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "task_executions",
        sa.Column("compensation_last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_executions",
        sa.Column("compensation_last_attempt_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "task_executions",
        sa.Column("compensation_locked_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "task_executions",
        sa.Column("compensation_lock_reason", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_executions", "compensation_lock_reason")
    op.drop_column("task_executions", "compensation_locked_at")
    op.drop_column("task_executions", "compensation_last_attempt_at")
    op.drop_column("task_executions", "compensation_last_error")
    op.drop_column("task_executions", "compensation_attempt_count")
