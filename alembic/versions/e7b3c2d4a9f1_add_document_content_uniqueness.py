"""为 documents 表增加独立生命周期状态轴、存储状态轴与有效内容哈希唯一约束。

业务背景与设计规范：
1. 三状态轴解耦：
   - `status`（处理流水线状态）：uploaded -> processing -> processed -> chunking -> chunked -> indexing -> indexed / failed。
   - `lifecycle_status`（业务生命周期）：scheduled / active / expired / replaced / deleted，将业务时效性与处理状态解耦。
   - `storage_status`（物理存储状态）：active / archived / purged。
2. 知识库内去重不变量：
   - 增加 `active_content_hash` 列，仅在文档处于激活态时维护内容哈希（非激活态置 NULL）。
   - 创建 `uq_documents_kb_active_content_hash (kb_id, active_content_hash)` 唯一索引，
     确保同一知识库内绝不存在内容完全相同的两个活跃文档，同时允许历史版本或已删除文档保留相同 hash。

Revision ID: e7b3c2d4a9f1
Revises: c5f12a3e9b71
Create Date: 2026-07-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7b3c2d4a9f1"
down_revision: Union[str, Sequence[str], None] = "c5f12a3e9b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加三状态轴字段，并将现有文档 content_hash 回填为 active_content_hash 后创建知识库唯一约束。"""
    op.add_column(
        "documents",
        sa.Column("active_content_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "lifecycle_status",
            sa.String(length=30),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "storage_status",
            sa.String(length=30),
            nullable=False,
            server_default="active",
        ),
    )

    op.execute(
        """
        UPDATE documents
        SET active_content_hash = content_hash
        """
    )

    op.create_unique_constraint(
        "uq_documents_kb_active_content_hash",
        "documents",
        ["kb_id", "active_content_hash"],
    )


def downgrade() -> None:
    """移除有效内容哈希约束和新增状态轴。"""
    op.drop_constraint(
        "uq_documents_kb_active_content_hash",
        "documents",
        type_="unique",
    )
    op.drop_column("documents", "storage_status")
    op.drop_column("documents", "lifecycle_status")
    op.drop_column("documents", "active_content_hash")
