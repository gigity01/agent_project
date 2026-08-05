"""Plan ORM 仓储。"""

from sqlalchemy.orm import Session

from app.modules.planning.infrastructure.persistence.models.plan import Plan


class PlanRepository:
    """只负责 Plan 查询、锁定和 flush，不提交事务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, plan: Plan) -> Plan:
        self.db.add(plan)
        self.db.flush()
        self.db.refresh(plan)
        return plan

    def get_by_id(self, plan_id: str) -> Plan | None:
        return (
            self.db.query(Plan)
            .filter(Plan.plan_id == plan_id)
            .first()
        )

    def get_by_turn_and_revision(
        self,
        turn_id: str,
        revision: int,
    ) -> Plan | None:
        return (
            self.db.query(Plan)
            .filter(
                Plan.turn_id == turn_id,
                Plan.revision == revision,
            )
            .first()
        )

    def get_by_id_for_update(self, plan_id: str) -> Plan | None:
        return (
            self.db.query(Plan)
            .filter(Plan.plan_id == plan_id)
            .with_for_update()
            .first()
        )

    def set_status(
        self,
        plan: Plan,
        *,
        status: str,
        failure_reason: str | None,
    ) -> Plan:
        plan.status = status
        plan.failure_reason = failure_reason
        self.db.flush()
        return plan
