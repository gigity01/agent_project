"""Task ORM 仓储。"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.modules.planning.infrastructure.persistence.models.task import Task


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

    def set_status(self, tasks: Iterable[Task], status: str) -> None:
        for task in tasks:
            task.status = status
        self.db.flush()
