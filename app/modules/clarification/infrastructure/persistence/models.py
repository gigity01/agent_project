"""ClarificationRequest ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base
from app.modules.clarification.domain.enums import ClarificationStatus


class ClarificationRequest(Base):
    __tablename__ = "clarification_requests"
    __table_args__ = (
        UniqueConstraint(
            "source_plan_id",
            name="uq_clarification_requests_source_plan",
        ),
    )

    clarification_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_turn_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("conversation_turns.turn_id"), nullable=False
    )
    source_plan_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("plans.plan_id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_information_json: Mapped[list] = mapped_column(JSON, nullable=False)
    known_resource_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ClarificationStatus.OPEN.value
    )
    answer_turn_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("conversation_turns.turn_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index(
    "idx_clarification_conversation_status",
    ClarificationRequest.conversation_id,
    ClarificationRequest.status,
)
