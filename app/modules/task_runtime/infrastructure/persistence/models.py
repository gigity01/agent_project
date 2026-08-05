"""TaskExecution ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base
from app.modules.task_runtime.domain.enums import TaskExecutionStatus


class TaskExecution(Base):
    __tablename__ = "task_executions"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "attempt",
            name="uq_task_executions_task_attempt",
        ),
    )

    execution_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("tasks.task_id"), nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("plans.plan_id"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(String(100), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=TaskExecutionStatus.RUNNING.value,
    )
    executor_code: Mapped[str] = mapped_column(String(100), nullable=False)
    input_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resource_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool | None] = mapped_column(nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("idx_task_executions_plan_status", TaskExecution.plan_id, TaskExecution.status)
