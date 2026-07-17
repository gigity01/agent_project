"""增加文档生命周期、存储状态和有效内容哈希。

Revision ID: e7b3c2d4a9f1
Revises: c5f12a3e9b71
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7b3c2d4a9f1"
down_revision: Union[str, Sequence[str], None] = "c5f12a3e9b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增状态轴并阻止同一知识库存在重复的有效内容哈希。"""
    if not context.is_offline_mode():
        duplicate = op.get_bind().execute(
            sa.text(
                """
                SELECT kb_id, content_hash, COUNT(*) AS duplicate_count
                FROM documents
                WHERE status <> 'expired'
                GROUP BY kb_id, content_hash
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError(
                "存在重复的有效文档 Hash，请先清理后再执行迁移；"
                f"kb_id={duplicate.kb_id}, count={duplicate.duplicate_count}"
            )

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
        SET active_content_hash = content_hash,
            lifecycle_status = 'active',
            storage_status = 'active'
        """
    )
    op.execute(
        """
        UPDATE documents
        SET active_content_hash = NULL,
            lifecycle_status = 'expired'
        WHERE status = 'expired'
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
