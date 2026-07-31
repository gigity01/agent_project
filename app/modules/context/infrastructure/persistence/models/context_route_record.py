"""Context Agent 路由决策的 SQLAlchemy ORM 定义。"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class ContextRouteRecord(Base):
    """保存经确定性校验后的路由决定及预分配新链 ID。"""

    __tablename__ = "context_route_decisions"
    __table_args__ = (
        UniqueConstraint(
            "current_turn_id",
            name="uq_context_route_decisions_turn",
        ),
    )

    route_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    current_turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    selected_chain_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    create_new_chain: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    route_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)
    new_chain_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    turn = relationship("ConversationTurn", back_populates="route_decision")


Index(
    "idx_context_route_decisions_conversation_created",
    ContextRouteRecord.conversation_id,
    ContextRouteRecord.created_at,
)
