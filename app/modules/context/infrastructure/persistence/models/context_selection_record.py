"""Context Selection 的 SQLAlchemy ORM 定义。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ContextSelectionRecord(Base):
    """保存经确定性校验的 Planner 历史 Context Read Set 决策记录的 ORM 实体。

    设计原则：
    - (current_turn_id) 唯一约束：确保每个 Turn 仅产生一条经过合法性校验的 Context Selection 事实。
    - relevant_chain_ids: 记录路由命中的所有历史链 ID。
    - selection_mode: 确定性推导的路由模式（如 single_match, multi_match, new_chain 等）。
    """

    __tablename__ = "context_selection_records"
    __table_args__ = (
        UniqueConstraint(
            "current_turn_id",
            name="uq_context_selection_records_turn",
        ),
    )

    selection_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    current_turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    relevant_chain_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    selection_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    turn = relationship("ConversationTurn", back_populates="context_selection")


Index(
    "idx_context_selection_records_conversation_created",
    ContextSelectionRecord.conversation_id,
    ContextSelectionRecord.created_at,
)
