"""Task ORM 仓储。"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.modules.planning.infrastructure.persistence.models.task import Task
from app.modules.planning.infrastructure.persistence.models.task_dependency import (
    TaskDependency,
)


class TaskRepository:
    """只负责 Task 查询、锁定和 flush，不提交事务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, task: Task) -> Task:
        self.db.add(task)
        self.db.flush()
        self.db.refresh(task)
        return task

    def list_by_plan_id(self, plan_id: str) -> list[Task]:
        return (
            self.db.query(Task)
            .filter(Task.plan_id == plan_id)
            .order_by(Task.sequence.asc(), Task.task_id.asc())
            .all()
        )

    def list_by_plan_id_and_status_for_update(
        self,
        plan_id: str,
        status: str,
    ) -> list[Task]:
        return (
            self.db.query(Task)
            .filter(
                Task.plan_id == plan_id,
                Task.status == status,
            )
            .order_by(Task.sequence.asc(), Task.task_id.asc())
            .with_for_update()
            .all()
        )

    def get_by_id_for_update(self, task_id: str) -> Task | None:
        return (
            self.db.query(Task)
            .filter(Task.task_id == task_id)
            .with_for_update()
            .first()
        )

    def get_next_runnable_for_update(
        self,
        plan_id: str,
        pending_status: str,
        succeeded_status: str,
    ) -> Task | None:
        candidates = (
            self.db.query(Task)
            .filter(Task.plan_id == plan_id, Task.status == pending_status)
            .order_by(Task.sequence.asc(), Task.task_id.asc())
            .with_for_update()
            .all()
        )
        for task in candidates:
            predecessor_ids = [
                row.depends_on_task_id
                for row in self.db.query(TaskDependency)
                .filter(TaskDependency.task_id == task.task_id)
                .all()
            ]
            if not predecessor_ids:
                return task
            succeeded_count = (
                self.db.query(Task)
                .filter(
                    Task.task_id.in_(predecessor_ids),
                    Task.status == succeeded_status,
                )
                .count()
            )
            if succeeded_count == len(predecessor_ids):
                return task
        return None

    def count_by_plan_and_status(self, plan_id: str, status: str) -> int:
        return (
            self.db.query(Task)
            .filter(Task.plan_id == plan_id, Task.status == status)
            .count()
        )

    def set_status(self, tasks: Iterable[Task], status: str) -> None:
        for task in tasks:
            task.status = status
        self.db.flush()

    def set_unfinished_status(self, plan_id: str, status: str) -> None:
        terminal = {"succeeded", "failed", "cancelled", "superseded"}
        tasks = self.db.query(Task).filter(Task.plan_id == plan_id).all()
        for task in tasks:
            if task.status not in terminal:
                task.status = status
        self.db.flush()
