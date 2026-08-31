"""为 documents 表增加 active_operation_id 列及对应索引。

业务背景与设计规范：
1. 操作所有权令牌（Ownership Token）：
   - 当 Task Runtime 领取处理/切块/索引任务并执行 Claim 事务时，将当前 TaskExecution 的 operation_id 写入 documents.active_operation_id。
2. 围栏与补偿隔离（Fencing & Compensation Boundary）：
   - 后续的 Finalize（正常完成）或 Compensator（失败补偿）必须强校验相同的 operation_id 令牌，只有持有当前令牌的操作才能提交状态或清理副作用，
     防止旧的超时执行或跨 Worker 并发写入破坏新 attempt 的数据完整性。

Revision ID: b1c3d5e7f9a2
Revises: a8d2e4f6b1c3
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c3d5e7f9a2"
down_revision: Union[str, Sequence[str], None] = "a8d2e4f6b1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """在 documents 表添加 active_operation_id 字段并建立普通查询索引。"""
    op.add_column(
        "documents",
        sa.Column(
            "active_operation_id",
            sa.String(length=100),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_documents_active_operation_id",
        "documents",
        ["active_operation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_active_operation_id",
        table_name="documents",
    )
    op.drop_column("documents", "active_operation_id")
