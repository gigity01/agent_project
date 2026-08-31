"""Context Chain 资源历史事件的 SQLAlchemy ORM 定义。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ContextChainResourceEvent(Base):
    """追加保存资源在某条 Chain 中的完整变化历史事件（seen, refreshed, removed, invalidated）的 ORM 实体。

    设计原则：
    - 作为不可变追加日志事实，记录每一次资源交互（首次发现、刷新活跃、移除停用或失效）。
    - 即使 Redis 缓存发生驱逐或失效，数据库内的全量事件记录永久保留。
    """

    __tablename__ = "context_chain_resource_events"

    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    chain_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("context_chains.chain_id"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    resource_key: Mapped[str] = mapped_column(String(512), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(400), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    relation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )


Index(
    "idx_context_resource_events_chain_resource_created",
    ContextChainResourceEvent.chain_id,
    ContextChainResourceEvent.resource_key,
    ContextChainResourceEvent.created_at,
)
Index(
    "idx_context_resource_events_turn",
    ContextChainResourceEvent.turn_id,
)
