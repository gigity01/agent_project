"""Plan 内 Task DAG 依赖边。"""

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class TaskDependency(Base):
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
