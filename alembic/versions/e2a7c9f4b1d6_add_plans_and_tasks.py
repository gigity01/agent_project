"""创建任务规划（plans）与任务执行实体（tasks）持久化表。

业务背景与设计规范：
1. `plans` 表：
   - 记录 Plan 实例与会话轮次（turn_id）的关联。
   - 通过 `uq_plans_turn_revision (turn_id, revision)` 保证同一轮次内 Plan revision 版本递增唯一，支持 Replan 重新生成。
2. `tasks` 表：
   - 记录 Task 实例、所属 Plan、关联轮次、能力标识（capability_code，如 process_document / build_document_chunks / index_document_vectors）、
     结构化输入参数（input_json）、顺序（sequence）与任务执行状态（status）。
   - 建立针对 `(plan_id, status, sequence)` 的索引支持按序领取可执行 Task。

Revision ID: e2a7c9f4b1d6
Revises: d4f8a1c7e2b9
Create Date: 2026-08-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2a7c9f4b1d6"
down_revision: Union[str, Sequence[str], None] = "d4f8a1c7e2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 plans 与 tasks 基础表及其索引与外键约束。"""
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
