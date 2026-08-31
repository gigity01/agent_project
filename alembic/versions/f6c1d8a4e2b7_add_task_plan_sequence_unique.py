"""为 tasks 表添加 (plan_id, sequence) 复合唯一约束。

业务背景与设计规范：
1. 规划业务不变量：每个 Plan 内部的 Task 序号必须从 1 开始连续且唯一递增。
2. 数据库级硬约束：在并发创建或重试规划时，防止因并发竞争导致同一 Plan 内部出现重复的 sequence。

Revision ID: f6c1d8a4e2b7
Revises: e2a7c9f4b1d6
Create Date: 2026-08-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6c1d8a4e2b7"
down_revision: Union[str, Sequence[str], None] = "e2a7c9f4b1d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 uq_tasks_plan_sequence 唯一约束，保证同一 Plan 下 sequence 的唯一性。"""
    op.create_unique_constraint(
        "uq_tasks_plan_sequence",
        "tasks",
        ["plan_id", "sequence"],
    )


def downgrade() -> None:
    """移除 Task sequence 唯一约束。"""
    op.drop_constraint(
        "uq_tasks_plan_sequence",
        "tasks",
        type_="unique",
    )
