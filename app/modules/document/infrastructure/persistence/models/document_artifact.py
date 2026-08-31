"""文档模块派生产物（DocumentArtifact）的 SQLAlchemy ORM 实体定义。

对应数据库表 `document_artifacts`。
记录文件处理转换过程中生成的派生文件（如 Docling 转换生成的 Markdown 二级文本、Processor 清洗后的标准文本等），
支持多版本管理与 superseded 状态标记。
"""

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

from app.infrastructure.database.base import Base


class DocumentArtifact(Base):
    """文档派生产物 ORM 模型。"""

    __tablename__ = "document_artifacts"

    # 自增主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 所属文档 ID
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 稳定业务编码（格式形如 art_xxx）
    artifact_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    # 产物类型（如 'secondary_text', 'cleaned_text'）
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 产物角色（如 'process_input', 'chunk_input'）
    artifact_role: Mapped[str] = mapped_column(String(50), nullable=False)
    # 产物文件格式（如 'md', 'txt', 'csv'）
    artifact_format: Mapped[str] = mapped_column(String(20), nullable=False)

    # 产物物理存储路径 URI
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)

    # 产物哈希值及算法
    artifact_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hash_algorithm: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 转换提供方（如 'docling'）与处理器类名
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    processor: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 产物统计元数据
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    char_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    line_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 状态（active / superseded / deleted）
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        server_default="active",
    )

    # 附加扩展元数据 JSON
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

    # 反向关联所属文档实体
    document = relationship("Document", back_populates="artifacts")


# 索引定义
Index(
    "idx_document_artifacts_type_role",
    DocumentArtifact.artifact_type,
    DocumentArtifact.artifact_role,
)

Index(
    "idx_document_artifacts_status",
    DocumentArtifact.status,
)
