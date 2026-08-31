"""以 SQLAlchemy ORM 模型元数据为准对齐数据库物理 Schema。

业务背景与变更内容：
1. `conversation_turns` 增加 `clarification_input` 文本列，用于在同一 Turn 内保存用户的澄清回复内容，无需创建第二个 Turn。
2. `child_chunks` 调整：新增 `idx_child_chunks_kb_id` 索引，清理过时的冗余索引与表级注释。
3. `document_artifacts` 调整：将 `idx_document_artifacts_document_id` 重命名为 `ix_document_artifacts_document_id`，清理冗余索引。
4. `documents`、`knowledge_bases`、`parent_blocks` 字段与索引清理：移除遗留的旧索引与废弃注释，使数据库结构与 ORM 映射完全保持一致。
5. 删除废弃的 `domains` 表。

Revision ID: 4ce8fd45dde4
Revises: f4a7c9e2b6d8
Create Date: 2026-08-20 17:11:45.411418
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '4ce8fd45dde4'
down_revision: Union[str, Sequence[str], None] = 'f4a7c9e2b6d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """使数据库物理 Schema 与当前 ORM metadata 完全一致。"""
    op.add_column(
        "conversation_turns",
        sa.Column("clarification_input", sa.Text(), nullable=True),
    )
    op.alter_column('child_chunks', 'section_path',
               existing_type=mysql.JSON(),
               comment=None,
               existing_comment='chunk 所在结构路径，可用于 md/html/pdf 等结构化文档',
               existing_nullable=True)
    op.create_index(
        "idx_child_chunks_kb_id",
        "child_chunks",
        ["kb_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            "ALTER TABLE child_chunks "
            "DROP INDEX idx_chunk_doc_status, "
            "DROP INDEX idx_chunk_domain_status, "
            "DROP INDEX idx_chunk_kb_status, "
            "DROP INDEX idx_chunk_parent_status, "
            "DROP INDEX idx_chunk_scene, "
            "DROP INDEX idx_chunk_vector_status"
        )
    )
    op.drop_table_comment(
        'child_chunks',
        existing_comment='子块表',
        schema=None
    )
    op.execute(
        sa.text(
            "ALTER TABLE document_artifacts "
            "RENAME INDEX idx_document_artifacts_document_id "
            "TO ix_document_artifacts_document_id, "
            "DROP INDEX idx_document_artifacts_document_type_role, "
            "DROP INDEX idx_document_artifacts_provider"
        )
    )
    op.alter_column('documents', 'source_type',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=50),
               comment=None,
               existing_comment='md/txt/pdf/csv/html',
               existing_nullable=False)
    op.alter_column('documents', 'source_uri',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=500),
               comment=None,
               existing_comment='原始文件保存路径',
               existing_nullable=False)
    op.alter_column('documents', 'cleaned_uri',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=500),
               comment=None,
               existing_comment='清洗后文件路径',
               existing_nullable=True)
    op.alter_column('documents', 'content_hash',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=128),
               comment=None,
               existing_comment='文件内容的hash值128',
               existing_nullable=False)
    op.alter_column('documents', 'status',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=30),
               comment=None,
               existing_comment='draft/indexing/active/failed/archived/deleted/replaced',
               existing_nullable=False,
               existing_server_default=sa.text("'draft'"))
    op.alter_column('documents', 'replaced_by',
               existing_type=mysql.BIGINT(),
               comment=None,
               existing_comment='被哪个新文档替代',
               existing_nullable=True)
    op.alter_column('documents', 'risk_level',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=30),
               comment=None,
               existing_comment='low/medium/high/critical',
               existing_nullable=True)
    op.alter_column('documents', 'effective_at',
               existing_type=mysql.DATETIME(),
               comment=None,
               existing_comment='生效时间',
               existing_nullable=True)
    op.alter_column('documents', 'expired_at',
               existing_type=mysql.DATETIME(),
               comment=None,
               existing_comment='失效时间',
               existing_nullable=True)
    op.alter_column('documents', 'created_by_actor_code',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=100),
               comment=None,
               existing_comment='上传人/创建主体',
               existing_nullable=True)
    op.alter_column('documents', 'original_filename',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=255),
               comment=None,
               existing_comment='用户上传时的原始文件名',
               existing_nullable=True)
    op.alter_column('documents', 'file_size',
               existing_type=mysql.BIGINT(),
               comment=None,
               existing_comment='文件大小，单位 byte',
               existing_nullable=True)
    op.alter_column('documents', 'mime_type',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=100),
               comment=None,
               existing_comment='上传文件 Content-Type，仅作辅助参考',
               existing_nullable=True)
    op.alter_column('documents', 'indexed_at',
               existing_type=mysql.DATETIME(),
               comment=None,
               existing_comment='索引完成时间',
               existing_nullable=True)
    op.execute(
        sa.text(
            "ALTER TABLE documents "
            "DROP INDEX idx_doc_domain_status, "
            "DROP INDEX idx_doc_hash, "
            "DROP INDEX idx_doc_kb_status, "
            "DROP INDEX idx_doc_scene"
        )
    )
    op.drop_table_comment(
        'documents',
        existing_comment='文档表',
        schema=None
    )
    op.alter_column('knowledge_bases', 'domain_code',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=100),
               comment=None,
               existing_comment='只能绑定可 RAG 检索的 external domain',
               existing_nullable=False)
    op.alter_column('knowledge_bases', 'business_scene',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=100),
               comment=None,
               existing_comment='refund/order/logistics 等业务场景',
               existing_nullable=True)
    op.alter_column('knowledge_bases', 'visibility',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=30),
               comment=None,
               existing_comment='external/internal/restricted',
               existing_nullable=False,
               existing_server_default=sa.text("'external'"))
    op.execute(
        sa.text(
            "ALTER TABLE knowledge_bases "
            "DROP INDEX idx_kb_domain_status, "
            "DROP INDEX idx_kb_scene"
        )
    )
    op.drop_table_comment(
        'knowledge_bases',
        existing_comment='知识库表',
        schema=None
    )
    op.alter_column('parent_blocks', 'block_type',
               existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_unicode_ci', length=50),
               comment=None,
               existing_comment='paragraph/markdown_section/html_section/pdf_section 等父级上下文类型',
               existing_nullable=False)
    op.execute(
        sa.text(
            "ALTER TABLE parent_blocks "
            "DROP INDEX idx_parent_doc_status, "
            "DROP INDEX idx_parent_domain_status, "
            "DROP INDEX idx_parent_scene"
        )
    )
    op.drop_table_comment(
        'parent_blocks',
        existing_comment='父块表',
        schema=None
    )
    # 数据删除放在最后；完整恢复必须使用升级前数据库备份。
    op.drop_table("domains")


def downgrade() -> None:
    """该迁移删除数据库独有数据，回退必须恢复升级前完整备份。"""
    raise RuntimeError(
        "ORM schema reconciliation is irreversible; restore the "
        "pre-upgrade database backup before running the previous version"
    )
