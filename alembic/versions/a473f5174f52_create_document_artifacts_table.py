"""创建文档派生产物表。

该表将二级文本、布局结果等可追溯产物与原始 Document 分离保存，支持同类
产物版本替换，同时保留历史记录供审计。

Revision ID: a473f5174f52
Revises: f9ea202ef500
Create Date: 2026-07-09 09:56:35.417378

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'a473f5174f52'
down_revision: Union[str, Sequence[str], None] = 'f9ea202ef500'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建派生产物表及其按文档、类型和状态查询所需的索引。"""
    op.create_table(
        "document_artifacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),

        sa.Column("document_id", sa.BigInteger(), nullable=False),

        sa.Column("artifact_code", sa.String(length=100), nullable=False),

        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("artifact_role", sa.String(length=50), nullable=False),
        sa.Column("artifact_format", sa.String(length=20), nullable=False),

        sa.Column("artifact_uri", sa.String(length=1024), nullable=False),

        sa.Column("artifact_hash", sa.String(length=128), nullable=True),
        sa.Column("hash_algorithm", sa.String(length=32), nullable=True),

        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("processor", sa.String(length=100), nullable=True),

        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("char_count", sa.BigInteger(), nullable=True),
        sa.Column("line_count", sa.BigInteger(), nullable=True),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="active",
        ),

        sa.Column("metadata", mysql.JSON(), nullable=True),

        sa.Column("created_by_actor_code", sa.String(length=80), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_code", name="uk_document_artifacts_artifact_code"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_artifacts_document_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "idx_document_artifacts_document_id",
        "document_artifacts",
        ["document_id"],
    )

    op.create_index(
        "idx_document_artifacts_type_role",
        "document_artifacts",
        ["artifact_type", "artifact_role"],
    )

    op.create_index(
        "idx_document_artifacts_document_type_role",
        "document_artifacts",
        ["document_id", "artifact_type", "artifact_role"],
    )

    op.create_index(
        "idx_document_artifacts_status",
        "document_artifacts",
        ["status"],
    )

    op.create_index(
        "idx_document_artifacts_provider",
        "document_artifacts",
        ["provider"],
    )


def downgrade() -> None:
    """按创建的逆序删除索引和派生产物表。"""
    op.drop_index("idx_document_artifacts_provider", table_name="document_artifacts")
    op.drop_index("idx_document_artifacts_status", table_name="document_artifacts")
    op.drop_index("idx_document_artifacts_document_type_role", table_name="document_artifacts")
    op.drop_index("idx_document_artifacts_type_role", table_name="document_artifacts")
    op.drop_index("idx_document_artifacts_document_id", table_name="document_artifacts")

    op.drop_table("document_artifacts")
