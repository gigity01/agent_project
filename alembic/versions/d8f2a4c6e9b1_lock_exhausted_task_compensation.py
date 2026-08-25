"""在 task_executions 表中增加补偿重试追踪与耗尽锁定字段。

业务背景与设计规范：
1. 补偿状态机追踪：
   - `compensation_attempt_count`：记录 Compensator 真实调用的尝试次数（含首次执行）。
   - `compensation_last_error`：记录补偿失败时的最新错误信息。
   - `compensation_last_attempt_at`：记录最后一次补偿尝试时间戳。
2. 补偿死锁防护（Compensation Lock）：
   - 当补偿尝试达到最大上限仍未成功时，写入 `compensation_locked_at` 和 `compensation_lock_reason`，
     使 TaskExecution 进入 `compensation_locked` 终态，并保持 Document ownership，禁止未解决副作用的并发接管，防止无限重试风暴。

Revision ID: d8f2a4c6e9b1
Revises: c2d4e6f8a0b1
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8f2a4c6e9b1"
down_revision: Union[str, Sequence[str], None] = "c2d4e6f8a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """在 task_executions 表中增加补偿重试计数、末次错误、尝试时间及锁定相关字段。"""
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
