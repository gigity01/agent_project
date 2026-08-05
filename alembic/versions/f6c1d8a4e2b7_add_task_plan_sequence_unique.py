"""保证同一 Plan 的 Task sequence 唯一。

Revision ID: f6c1d8a4e2b7
Revises: e2a7c9f4b1d6
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f6c1d8a4e2b7"
down_revision: Union[str, Sequence[str], None] = "e2a7c9f4b1d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加并发写入时的最终 sequence 唯一性保护。"""
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
