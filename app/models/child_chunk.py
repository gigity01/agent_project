"""用于向量化和检索的文档子块 SQLAlchemy ORM 定义。"""

from datetime import datetime

from sqlalchemy import BigInteger, String, DateTime, Integer, ForeignKey, Index, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class ChildChunk(Base):
    """保存可独立向量化的文本片段及其索引状态。"""
    __tablename__ = "child_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chunk_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    parent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parent_blocks.id"), nullable=False)
    doc_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id"), nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_bases.id"), nullable=False)

    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ``chunk_index`` 只在同一父块内排序；全局顺序由父块的 ``block_index`` 决定。
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    section_path: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    source_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_text: Mapped[str] = mapped_column(Text, nullable=False)

    # 向量状态将关系库的任务状态与 Qdrant 写入结果关联，支持失败后按块重试。
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    qdrant_point_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index(
    "idx_child_chunks_parent_chunk_index",
    ChildChunk.parent_id,
    ChildChunk.chunk_index,
)

Index(
    "idx_child_chunks_doc_vector_status",
    ChildChunk.doc_id,
    ChildChunk.vector_status,
    ChildChunk.status,
)
