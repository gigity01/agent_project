"""原始文档及其处理状态的 SQLAlchemy ORM 定义。"""

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

from app.db.session import Base
from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_storage_status import DocumentStorageStatus
from app.constants.document_status import DocumentStatus


class Document(Base):
    """保存上传文件、清洗文件和文档生命周期元数据。"""
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "kb_id",
            "active_content_hash",
            name="uq_documents_kb_active_content_hash",
        ),
    )

    # 稳定业务编号用于文件名、审计日志和外部引用；数值主键仅用于数据库关联。
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_bases.id"), nullable=False)
    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # ``source_uri`` 指向原件，``cleaned_uri`` 指向可直接切块的标准化文本。
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    cleaned_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)

    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    active_content_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # status 只表示处理进度；业务有效性和文件存储位置由独立状态轴维护。
    lifecycle_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DocumentLifecycleStatus.ACTIVE.value,
    )
    storage_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DocumentStorageStatus.ACTIVE.value,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 状态由上传、处理、切块和索引服务推进；不要只依靠某个 URI 是否为空判断。
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
    )
    replaced_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    risk_level: Mapped[str | None] = mapped_column(String(30), nullable=True)

    effective_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    created_by_actor_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
