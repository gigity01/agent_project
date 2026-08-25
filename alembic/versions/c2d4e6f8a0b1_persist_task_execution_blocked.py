"""在 task_executions 表中增加 blocked 布尔字段。

业务背景与设计规范：
1. 任务终态区分：
   - 区别于可重试失败（retryable=True）与普通失败（status=failed），当 Task 执行被明确拒绝（如 Command Tool 返回 rejected、权限不匹配或业务前置条件不满足）时，
     将 `blocked` 置为 True。
2. 触发即时 Replan：
   - 阻塞态 Execution 表明继续重试无法取得进展，Runtime 将直接触发不可重试失败流程并请求生成新 Plan revision。

Revision ID: c2d4e6f8a0b1
Revises: b1c3d5e7f9a2
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d4e6f8a0b1"
down_revision: Union[str, Sequence[str], None] = "b1c3d5e7f9a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """在 task_executions 表中增加 blocked 布尔列，默认为 False。"""
    op.add_column(
        "task_executions",
        sa.Column(
            "blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("task_executions", "blocked")
