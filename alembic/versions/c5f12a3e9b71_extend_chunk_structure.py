"""扩展父子块的语义恢复与检索上下文字段。

Revision ID: c5f12a3e9b71
Revises: a473f5174f52
Create Date: 2026-07-13 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5f12a3e9b71"
down_revision: Union[str, Sequence[str], None] = "a473f5174f52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加语义组、组内顺序以及子块检索上下文字段和索引。"""
    op.add_column(
        "parent_blocks",
        sa.Column(
            "semantic_group_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "parent_blocks",
        sa.Column(
            "segment_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "child_chunks",
        sa.Column("section_path", sa.JSON(), nullable=True),
    )
    op.add_column(
        "child_chunks",
        sa.Column("source_row_index", sa.Integer(), nullable=True),
    )

    op.create_index(
        "idx_parent_blocks_doc_group_segment",
        "parent_blocks",
        ["doc_id", "semantic_group_index", "segment_index"],
    )
    op.create_index(
        "idx_parent_blocks_doc_block_index",
        "parent_blocks",
        ["doc_id", "block_index"],
    )
    op.create_index(
        "idx_child_chunks_parent_chunk_index",
        "child_chunks",
        ["parent_id", "chunk_index"],
    )
    op.create_index(
        "idx_child_chunks_doc_vector_status",
        "child_chunks",
        ["doc_id", "vector_status", "status"],
    )


def downgrade() -> None:
    """按创建逆序移除索引和新增字段。"""
    op.drop_index(
        "idx_child_chunks_doc_vector_status",
        table_name="child_chunks",
    )
    op.drop_index(
        "idx_child_chunks_parent_chunk_index",
        table_name="child_chunks",
    )
    op.drop_index(
        "idx_parent_blocks_doc_block_index",
        table_name="parent_blocks",
    )
    op.drop_index(
        "idx_parent_blocks_doc_group_segment",
        table_name="parent_blocks",
    )

    op.drop_column("child_chunks", "source_row_index")
    op.drop_column("child_chunks", "section_path")
    op.drop_column("parent_blocks", "segment_index")
    op.drop_column("parent_blocks", "semantic_group_index")
