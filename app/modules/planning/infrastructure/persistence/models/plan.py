"""Plan 的 SQLAlchemy ORM 定义。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base
from app.modules.planning.domain.enums import PlanStatus


class Plan(Base):
    """保存一次 Turn 的一个规划 revision。"""

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint(
            "turn_id",
            "revision",
            name="uq_plans_turn_revision",
        ),
    )

    plan_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=PlanStatus.PLANNING.value,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    tasks = relationship("Task", back_populates="plan")


Index("idx_plans_turn_status", Plan.turn_id, Plan.status)
