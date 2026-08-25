"""扩展父级语义块（parent_blocks）与子块（child_chunks）的语义切分与上下文结构字段。

业务背景与设计规范：
1. `parent_blocks` 扩展：
   - `semantic_group_index`：语义分组序号（如 CSV 批量分组、多段落合并大语义块）。
   - `segment_index`：同一语义组内的切片顺序。
   - 增加 `(doc_id, semantic_group_index, segment_index)` 与 `(doc_id, block_index)` 索引，支持高效检索与顺序装配。
2. `child_chunks` 扩展：
   - `section_path`：记录 Markdown 标题层级路径（如 `["一级标题", "二级标题"]`），保留子块在结构化文档中的语义层级。
   - `source_row_index`：记录表格类数据（如 CSV）的原始数据行号。
   - 增加 `(parent_id, chunk_index)` 与 `(doc_id, vector_status, status)` 索引，加速向量索引任务筛选与父子关系关联。

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
    """添加语义组、分段索引及子块层级路径字段，并构建支持向量索引与父子块检索的高性能复合索引。"""
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
