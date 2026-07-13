"""原始文档及其处理状态的 SQLAlchemy ORM 定义。"""

from sqlalchemy import (
    BigInteger,
    String,
    DateTime,
    Integer,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.constants.document_status import DocumentStatus


class Document(Base):
    """保存上传文件、清洗文件和文档生命周期元数据。"""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_bases.id"), nullable=False)
    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    cleaned_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)

    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

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
