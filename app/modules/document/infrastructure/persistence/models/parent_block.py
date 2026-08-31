"""文档模块父级语义块（ParentBlock）的 SQLAlchemy ORM 实体定义。

对应数据库表 `parent_blocks`。
保存按自然段落或 Markdown 章节聚合的较完整语义上下文块（最大 4,000 字符，CSV 最多 50 行/12,000 字符），
供检索后溯源或上卷召回使用。
"""

from datetime import datetime

from sqlalchemy import BigInteger, String, DateTime, Integer, ForeignKey, Index, JSON
from sqlalchemy.dialects.mysql import MEDIUMTEXT, CHAR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ParentBlock(Base):
    """父级语义块 ORM 模型。"""

    __tablename__ = "parent_blocks"

    # 自增主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 稳定业务编码（格式形如 par_xxx）
    parent_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_bases.id"), nullable=False)
    doc_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id"), nullable=False)
    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 块类型（如 'section', 'paragraph', 'csv_rows'）
    block_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 章节或段落标题
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 章节层级面包屑路径 JSON 数组
    section_path: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # 父块完整正文内容
    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    # 内容 MD5 哈希
    content_hash: Mapped[str | None] = mapped_column(CHAR(32), nullable=True)

    # 全局块顺序索引（从 0 开始）
    block_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 语义组序号（如对应第几个章节或段落）
    semantic_group_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    # 同一语义组内部的分段序号
    segment_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    # 逻辑状态（active / inactive）
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


# 索引定义
Index(
    "idx_parent_blocks_doc_group_segment",
    ParentBlock.doc_id,
    ParentBlock.semantic_group_index,
    ParentBlock.segment_index,
)

Index(
    "idx_parent_blocks_doc_block_index",
    ParentBlock.doc_id,
    ParentBlock.block_index,
)
