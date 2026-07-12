"""文档处理过程中产生的派生文件 ORM 定义。"""

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DocumentArtifact(Base):
    """记录转换文本、布局结果等可追溯的文档派生产物。"""
    __tablename__ = "document_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    artifact_code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)

    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_role: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_format: Mapped[str] = mapped_column(String(20), nullable=False)

    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)

    artifact_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hash_algorithm: Mapped[str | None] = mapped_column(String(32), nullable=True)

    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    processor: Mapped[str | None] = mapped_column(String(100), nullable=True)

    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    char_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    line_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created")

    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    created_by_actor_code: Mapped[str | None] = mapped_column(String(80), nullable=True)

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

    document = relationship("Document", back_populates="artifacts")


Index(
    "idx_document_artifacts_type_role",
    DocumentArtifact.artifact_type,
    DocumentArtifact.artifact_role,
)

Index(
    "idx_document_artifacts_status",
    DocumentArtifact.status,
)
