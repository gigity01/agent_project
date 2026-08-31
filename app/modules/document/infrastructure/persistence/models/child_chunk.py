"""文档模块可向量化子切块（ChildChunk）的 SQLAlchemy ORM 定义。

对应数据库表 `child_chunks`。
存储子块正文（content）、拼接了章节路径的待向量化正文（embedding_text）、
向量化状态（vector_status: pending/indexing/indexed/failed）、以及与 Qdrant point_id 的一一对应映射（str(child_chunks.id)）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, String, DateTime, Integer, ForeignKey, Index, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ChildChunk(Base):
    """可向量化子块 ORM 模型，表示检索与 Embedding 计算的最小粒度实体。"""

    __tablename__ = "child_chunks"

    # 主键 ID（与 Qdrant Point ID 保持 1:1 映射）
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 稳定业务编号（格式形如 chk_xxx）
    chunk_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    parent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parent_blocks.id"), nullable=False)
    doc_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id"), nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_bases.id"), nullable=False)

    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 同一父块内的局部排序序号（从 0 开始）
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 子块类型（如 'text', 'csv_row'）
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    # 章节路径面包屑 JSON 数组
    section_path: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # 若为 CSV 格式，记录源文件 1-based 数据行号
    source_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 纯净正文切片（最大 600 字符，CSV 最大 8,000 字符）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 待输入向量模型的文本（拼接了 '标题路径：...\\n正文：...'）
    embedding_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Token 估计数
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 向量化处理状态（pending -> indexing -> indexed / failed）
    vector_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # Qdrant Point ID 字符串（等同于 str(id)）
    qdrant_point_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 逻辑活跃状态（active / inactive）
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    # 乐观锁版本号
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


# 索引定义
Index(
    "idx_child_chunks_kb_id",
    ChildChunk.kb_id,
)

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
