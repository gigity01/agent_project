"""文档主表（Document）的 SQLAlchemy ORM 实体定义。

对应数据库表 `documents`。
维护文档三状态轴（技术流水线状态 status、业务生命周期状态 lifecycle_status、底层存储状态 storage_status）、
操作所有权 token（active_operation_id）、知识库内唯一内容哈希约束（uq_documents_kb_active_content_hash）以及关联的派生产物。
"""

from sqlalchemy import (
    BigInteger,
    String,
    DateTime,
    Integer,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base
from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStatus,
    DocumentStorageStatus,
)


class Document(Base):
    """文档主实体 ORM 模型。"""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "kb_id",
            "active_content_hash",
            name="uq_documents_kb_active_content_hash",
        ),
    )

    # 数据库自增主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 稳定业务编码（格式形如 doc_xxx）
    doc_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_bases.id"), nullable=False)
    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 文档显示标题
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # 原始文件格式（如 'txt', 'md', 'pdf', 'docx', 'csv' 等）
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 原始落盘文件路径 URI
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    # 清洗/转换后的标准化文本文件路径 URI
    cleaned_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 原始文件 SHA-256 哈希
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # 活跃状态内容哈希（失效/软删除时置为 None 以释放知识库查重占用）
    active_content_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # 状态轴 2：业务生命周期状态（scheduled / active / expired / replaced / deleted）
    lifecycle_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DocumentLifecycleStatus.ACTIVE.value,
    )
    # 状态轴 3：底层物理存储状态（active / archiving / archived / deleted）
    storage_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DocumentStorageStatus.ACTIVE.value,
    )
    # 乐观锁版本号
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 状态轴 1：流水线技术处理状态（uploaded -> processing -> processed -> chunking -> chunked -> indexing -> indexed）
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
    )
    # 操作所有权 Token（持有该 operation_id 的任务才可推进或补偿状态）
    active_operation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    # 替代当前文档的新文档 ID
    replaced_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    risk_level: Mapped[str | None] = mapped_column(String(30), nullable=True)

    effective_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    created_by_actor_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 关联的派生产物集合
    artifacts = relationship(
        "DocumentArtifact",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    indexed_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
