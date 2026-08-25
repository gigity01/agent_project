"""Task 的 SQLAlchemy ORM 定义。

映射 `tasks` 数据表，记录 Planner 生成的单项具体能力执行任务及其实时状态。
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base
from app.modules.planning.domain.enums import TaskStatus


class Task(Base):
    """保存 Planner 生成的一项可执行能力调用实体。

    Attributes:
        task_id: 任务全局唯一标识，主键。
        plan_id: 所属 Plan ID 外键。
        turn_id: 所属 ConversationTurn 外键。
        task_ref: Plan 内唯一的任务局部引用标识（如 task_1）。
        capability_code: 目标领域能力编码（如 process_document）。
        input_json: 任务执行输入参数 JSON 字典。
        sequence: 任务在 Plan 内的执行序号，从 1 开始严格连续递增。
        status: 任务生命周期状态（TaskStatus）。
        attempt_count: 已尝试执行次数。
        max_attempts: 允许的最大尝试次数（默认为 3）。
        output_json: 任务执行成功后的输出结果 JSON 字典。
        last_error_code: 最近一次执行失败的错误分类码。
        last_error_message: 最近一次执行失败的错误详细信息。
        started_at: 任务首次被 Claim 开始执行的时间。
        completed_at: 任务终态完成时间。
        created_at: 任务创建时间。
        updated_at: 任务更新时间。
        plan: 与所属 Plan 实体的反向关系。
    """

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "sequence",
            name="uq_tasks_plan_sequence",
        ),
        UniqueConstraint(
            "plan_id",
            "task_ref",
            name="uq_tasks_plan_task_ref",
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
    task_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    capability_code: Mapped[str] = mapped_column(String(100), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=TaskStatus.DRAFT.value,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    last_error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
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

    plan = relationship(
        "Plan",
        back_populates="tasks",
        foreign_keys=[plan_id],
    )


Index("idx_tasks_plan_status_sequence", Task.plan_id, Task.status, Task.sequence)
Index("idx_tasks_turn_status", Task.turn_id, Task.status)
