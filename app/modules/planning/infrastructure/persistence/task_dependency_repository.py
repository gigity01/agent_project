"""TaskDependency 仓储。"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.modules.planning.infrastructure.persistence.models.task_dependency import (
    TaskDependency,
)


class TaskDependencyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_all(self, dependencies: Iterable[TaskDependency]) -> None:
        self.db.add_all(list(dependencies))
        self.db.flush()

    def list_by_plan_id(self, plan_id: str) -> list[TaskDependency]:
        return (
            self.db.query(TaskDependency)
            .filter(TaskDependency.plan_id == plan_id)
            .all()
        )
