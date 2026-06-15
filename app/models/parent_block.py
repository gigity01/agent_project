from datetime import datetime

from sqlalchemy import BigInteger, String, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.dialects.mysql import MEDIUMTEXT, CHAR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class ParentBlock(Base):
    __tablename__ = "parent_blocks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_bases.id"), nullable=False)
    doc_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id"), nullable=False)
    domain_code: Mapped[str] = mapped_column(String(100), nullable=False)
    business_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)

    block_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section_path: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(CHAR(32), nullable=True)

    block_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
