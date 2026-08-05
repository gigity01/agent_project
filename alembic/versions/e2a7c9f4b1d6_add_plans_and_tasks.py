"""增加 Plan 与 Task 规划持久化表。

Revision ID: e2a7c9f4b1d6
Revises: d4f8a1c7e2b9
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a7c9f4b1d6"
down_revision: Union[str, Sequence[str], None] = "d4f8a1c7e2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建规划记录和暂不包含依赖边的 Task。"""
    op.create_table(
        "plans",
        sa.Column("plan_id", sa.String(length=100), nullable=False),
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["conversation_turns.turn_id"],
        ),
        sa.PrimaryKeyConstraint("plan_id"),
        sa.UniqueConstraint(
            "turn_id",
            "revision",
            name="uq_plans_turn_revision",
        ),
    )
    op.create_index(
        "idx_plans_turn_status",
        "plans",
        ["turn_id", "status"],
        unique=False,
    )

    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(length=100), nullable=False),
        sa.Column("plan_id", sa.String(length=100), nullable=False),
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("capability_code", sa.String(length=100), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.plan_id"]),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["conversation_turns.turn_id"],
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(
        "idx_tasks_plan_status_sequence",
        "tasks",
        ["plan_id", "status", "sequence"],
        unique=False,
    )
    op.create_index(
        "idx_tasks_turn_status",
        "tasks",
        ["turn_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """按依赖逆序移除 Task 与 Plan。"""
    op.drop_index("idx_tasks_turn_status", table_name="tasks")
    op.drop_index("idx_tasks_plan_status_sequence", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("idx_plans_turn_status", table_name="plans")
    op.drop_table("plans")
