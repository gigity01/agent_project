"""Task 的 SQLAlchemy ORM 定义。"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base
from app.modules.planning.domain.enums import TaskStatus


class Task(Base):
    """保存 Planner 生成的一项可执行能力调用。"""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "sequence",
            name="uq_tasks_plan_sequence",
        ),
    )

    task_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("plans.plan_id"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    capability_code: Mapped[str] = mapped_column(String(100), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=TaskStatus.DRAFT.value,
    )
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

    plan = relationship("Plan", back_populates="tasks")


Index("idx_tasks_plan_status_sequence", Task.plan_id, Task.status, Task.sequence)
Index("idx_tasks_turn_status", Task.turn_id, Task.status)
