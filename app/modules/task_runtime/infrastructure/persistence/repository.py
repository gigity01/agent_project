"""TaskExecution 仓储。"""

from sqlalchemy.orm import Session

from app.modules.task_runtime.infrastructure.persistence.models import (
    TaskExecution,
)


class TaskExecutionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, execution: TaskExecution) -> TaskExecution:
        self.db.add(execution)
        self.db.flush()
        return execution

    def get_by_id_for_update(self, execution_id: str) -> TaskExecution | None:
        return (
            self.db.query(TaskExecution)
            .filter(TaskExecution.execution_id == execution_id)
            .with_for_update()
            .first()
        )

    def list_by_plan_id(self, plan_id: str) -> list[TaskExecution]:
        return (
            self.db.query(TaskExecution)
            .filter(TaskExecution.plan_id == plan_id)
            .order_by(TaskExecution.started_at.asc())
            .all()
        )

    def get_latest_running_by_task_for_update(
        self,
        task_id: str,
    ) -> TaskExecution | None:
        return (
            self.db.query(TaskExecution)
            .filter(
                TaskExecution.task_id == task_id,
                TaskExecution.status == "running",
            )
            .order_by(TaskExecution.attempt.desc())
            .with_for_update()
            .first()
        )

    def get_latest_by_task_for_update(
        self,
        task_id: str,
    ) -> TaskExecution | None:
        return (
            self.db.query(TaskExecution)
            .filter(TaskExecution.task_id == task_id)
            .order_by(TaskExecution.attempt.desc())
            .with_for_update()
            .first()
        )
