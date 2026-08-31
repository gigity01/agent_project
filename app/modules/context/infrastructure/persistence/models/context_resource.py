"""Context Chain 资源当前状态的 SQLAlchemy ORM 定义。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ContextChainResource(Base):
    """保存一条 Chain 历史资源的当前有效状态和使用统计的 ORM 实体。

    设计原则：
    - 作为全量事实层，采用 `UNIQUE(chain_id, resource_key)` 约束保证每条链对同一资源只有一条当前状态记录。
    - 记录资源的首次与最近引用 Turn（first_seen_turn_id, last_seen_turn_id）、活跃时间戳与使用频次（use_count）。
    - 显式停用时置 `active=False` 并记录 `removed_at`，不物理删除历史事实。
    """

    __tablename__ = "context_chain_resources"
    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "resource_key",
            name="uq_context_chain_resources_chain_resource",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    chain_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("context_chains.chain_id"),
        nullable=False,
    )
    resource_key: Mapped[str] = mapped_column(String(512), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(400), nullable=False)
    relation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    last_seen_turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    use_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


Index(
    "idx_context_chain_resources_chain_active_seen",
    ContextChainResource.chain_id,
    ContextChainResource.active,
    ContextChainResource.last_seen_at,
)
