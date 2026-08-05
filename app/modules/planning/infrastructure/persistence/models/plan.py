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
        UniqueConstraint(
            "workflow_id",
            "revision",
            name="uq_plans_workflow_revision",
        ),
    )

    plan_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(100), nullable=False)
    turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    parent_plan_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("plans.plan_id"),
        nullable=True,
    )
    current_task_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey(
            "tasks.task_id",
            name="fk_plans_current_task_id",
            use_alter=True,
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=PlanStatus.PLANNING.value,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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

    tasks = relationship(
        "Task",
        back_populates="plan",
        foreign_keys="Task.plan_id",
    )


Index("idx_plans_turn_status", Plan.turn_id, Plan.status)
Index("idx_plans_workflow_revision", Plan.workflow_id, Plan.revision)
