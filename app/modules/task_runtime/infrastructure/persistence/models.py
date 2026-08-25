"""TaskExecution ORM 模型定义。

映射 `task_executions` 数据表，持久化记录每次任务执行尝试的输入快照、
执行状态、产物、审计标识、Operation ownership token 以及补偿尝试历史。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base
from app.modules.task_runtime.domain.enums import TaskExecutionStatus


class TaskExecution(Base):
    """保存单次 Task 尝试执行（attempt）的执行快照与补偿生命周期实体。

    Attributes:
        execution_id: 执行尝试全局唯一 ID，主键。
        task_id: 所属 Task ID 外键。
        plan_id: 所属 Plan ID 外键。
        workflow_id: 所属工作流 ID。
        attempt: 执行尝试序号（从 1 开始）。
        status: 执行生命周期状态（TaskExecutionStatus）。
        executor_code: 执行所采用的 Executor 编码。
        input_snapshot_json: 执行时的不可变任务输入参数快照。
        output_json: 执行成功后的产出数据 JSON。
        resource_refs_json: 本次执行涉及的资源引用列表 JSON。
        error_code: 执行失败时的错误分类码。
        error_message: 执行失败时的错误详细描述。
        retryable: 失败是否可重试。
        blocked: 失败是否属于业务前置阻塞。
        agent_run_id: 关联的 Agents SDK / LLM Run 追踪 ID。
        operation_id: 关联的 Document Operation ID（即副作用 ownership token）。
        compensation_attempt_count: 已实际执行补偿的真实调用次数。
        compensation_last_error: 最近一次补偿失败的错误信息。
        compensation_last_attempt_at: 最近一次补偿尝试时间。
        compensation_locked_at: 补偿生命周期被锁定的时间（若适用）。
        compensation_lock_reason: 补偿被锁定的原因分类（CompensationLockReason）。
        started_at: 执行开始时间。
        completed_at: 执行完成或终态时间。
    """

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
    blocked: Mapped[bool] = mapped_column(nullable=False, default=False)
    agent_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    compensation_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    compensation_last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    compensation_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    compensation_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    compensation_lock_reason: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("idx_task_executions_plan_status", TaskExecution.plan_id, TaskExecution.status)
