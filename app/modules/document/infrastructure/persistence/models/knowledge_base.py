"""文档模块知识库主表（KnowledgeBase）的 SQLAlchemy ORM 实体定义。

对应数据库表 `knowledge_bases`。
保存知识库的业务编码、领域信息、可见性范围及向量集合（vector_collection）配置。
"""

from sqlalchemy import BigInteger, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class KnowledgeBase(Base):
    """知识库主实体 ORM 模型。"""

    __tablename__ = "knowledge_bases"

    # 自增主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 稳定业务编码（格式形如 kb_xxx）
    kb_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # 知识库名称
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 业务领域编码与业务场景
    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 描述文本
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 状态（active / inactive / archived）
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    # 可见性（internal / external / private）
    visibility: Mapped[str] = mapped_column(String(30), nullable=False, default="external")

    owner_actor_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 使用的 Embedding 模型名称（如 text-embedding-v3）
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    # 绑定的 Qdrant Collection 集合名称（默认 'knowledge_chunks'）
    vector_collection: Mapped[str] = mapped_column(String(100), nullable=False, default="knowledge_chunks")

    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
