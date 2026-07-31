"""Conversation Turn 的 SQLAlchemy ORM 定义。"""

from datetime import datetime

from sqlalchemy import DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ConversationTurn(Base):
    """保存一次完整用户输入及其唯一的助手处理结果。"""

    __tablename__ = "conversation_turns"

    turn_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_compact: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    task_result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    nodes = relationship("ContextChainNode", back_populates="turn")
    route_decision = relationship(
        "ContextRouteRecord",
        back_populates="turn",
        uselist=False,
    )


Index(
    "idx_conversation_turns_conversation_created",
    ConversationTurn.conversation_id,
    ConversationTurn.created_at,
)
