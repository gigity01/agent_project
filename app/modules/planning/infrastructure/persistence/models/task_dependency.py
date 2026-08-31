"""Plan 内 Task DAG 依赖边 ORM 定义。

映射 `task_dependencies` 数据表，记录同一个 Plan 内任务之间的有向依赖边，
支持拓扑排序与依赖满足性检查。
"""

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class TaskDependency(Base):
    """Task 有向依赖边持久化实体。

    表示 `task_id` 依赖于 `depends_on_task_id`（即 `depends_on_task_id` 必须先成功执行）。

    Attributes:
        dependency_id: 依赖边全局唯一主键。
        plan_id: 所属 Plan ID 外键。
        task_id: 后续任务 ID（当前任务）。
        depends_on_task_id: 前置依赖任务 ID。
    """

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "depends_on_task_id",
            name="uq_task_dependencies_edge",
        ),
        CheckConstraint(
            "task_id <> depends_on_task_id",
            name="ck_task_dependencies_no_self",
        ),
    )

    dependency_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("plans.plan_id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("tasks.task_id"), nullable=False
    )
    depends_on_task_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("tasks.task_id"), nullable=False
    )
