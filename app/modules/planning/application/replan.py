"""Replan 事件的幂等新 revision 编排。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from app.modules.context.domain.enums import ContextTurnStatus
from app.modules.messaging.application.inbox import record_inbox_once
from app.modules.planning.application.dto import (
    RunPlanningInput,
    RunPlanningResult,
)
from app.modules.planning.application.ports import PlanningApplicationPorts
from app.modules.planning.application.run_planning import RunPlanningUseCase
from app.modules.planning.domain.enums import PlanStatus, TaskStatus


MAX_PLAN_REVISIONS = 3
PLANNER_RUN_LEASE_SECONDS = 1800


@dataclass(frozen=True)
class ReplanRequested:
    event_id: str
    workflow_id: str
    conversation_id: str
    root_turn_id: str
    previous_plan_id: str
    next_revision: int
    trigger_type: str
    source_task_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReplanUseCase:
    """处理 Replan（重新规划）事件的用例。

    主流程：
    1. 校验最大 revision 限制（最多允许 3 次修订）。
    2. 使用 Inbox 实现事件幂等去重，防止重复触发 Replan。
    3. 行锁锁定前一 Plan，将未完成旧任务标记为 SUPERSEDED。
    4. 原子创建下一版本 Plan 记录（初始状态为 PLANNING）。
    5. 调用 RunPlanningUseCase.execute_existing 触发新一轮 Planner 规划。
    """

    CONSUMER_NAME = "planning.replan"

    def __init__(
        self,
        *,
        ports: PlanningApplicationPorts,
        run_planning: RunPlanningUseCase,
    ) -> None:
        self._ports = ports
        self._run_planning = run_planning

    async def execute(
        self,
        event: ReplanRequested,
    ) -> RunPlanningResult | None:
        """执行 Replan 事件处理，生成新 revision Plan 并重新规划。"""
        prepared = self._prepare_revision(event)
        if prepared is None:
            return None
        plan_id, revision = prepared
        return await self._run_planning.execute_existing(
            RunPlanningInput(
                conversation_id=event.conversation_id,
                turn_id=event.root_turn_id,
                revision=revision,
                workflow_id=event.workflow_id,
                parent_plan_id=event.previous_plan_id,
            ),
            plan_id,
        )

    def _prepare_revision(
        self,
        event: ReplanRequested,
    ) -> tuple[str, int] | None:
        with self._ports.uow_factory() as uow:
            if uow.inbox.exists(self.CONSUMER_NAME, event.event_id):
                existing = uow.plans.get_by_workflow_and_revision_for_update(
                    event.workflow_id,
                    event.next_revision,
                )
                if (
                    existing is None
                    or existing.status != PlanStatus.PLANNING.value
                ):
                    return None
                if datetime.now() < existing.updated_at + timedelta(
                    seconds=PLANNER_RUN_LEASE_SECONDS
                ):
                    return None
                existing.updated_at = datetime.now()
                uow.commit()
                return existing.plan_id, existing.revision
            previous = uow.plans.get_by_id_for_update(event.previous_plan_id)
            turn = uow.conversation_turns.get_by_id_for_update(
                event.root_turn_id
            )
            if previous is None or turn is None:
                raise ValueError("Replan 关联的 Plan 或 Turn 不存在")
            if (
                previous.workflow_id != event.workflow_id
                or turn.conversation_id != event.conversation_id
            ):
                raise ValueError("Replan 关联上下文不一致")
            if event.next_revision > MAX_PLAN_REVISIONS:
                previous.status = PlanStatus.FAILED.value
                previous.failure_code = "max_plan_revisions_exceeded"
                previous.failure_reason = "Plan revision 次数已达上限"
                previous.completed_at = datetime.now()
                uow.tasks.set_unfinished_status(
                    previous.plan_id, TaskStatus.FAILED.value
                )
                uow.conversation_turns.set_status(
                    turn, ContextTurnStatus.FAILED.value
                )
                record_inbox_once(
                    uow,
                    inbox_event_factory=self._ports.inbox_event_factory,
                    consumer_name=self.CONSUMER_NAME,
                    event_id=event.event_id,
                )
                uow.commit()
                return None

            existing = uow.plans.get_by_workflow_and_revision(
                event.workflow_id,
                event.next_revision,
            )
            if existing is not None:
                record_inbox_once(
                    uow,
                    inbox_event_factory=self._ports.inbox_event_factory,
                    consumer_name=self.CONSUMER_NAME,
                    event_id=event.event_id,
                )
                uow.commit()
                return (
                    (existing.plan_id, existing.revision)
                    if existing.status == PlanStatus.PLANNING.value
                    else None
                )

            previous.status = PlanStatus.SUPERSEDED.value
            previous.completed_at = datetime.now()
            uow.tasks.set_unfinished_status(
                previous.plan_id, TaskStatus.SUPERSEDED.value
            )
            plan_id = f"plan_{uuid4().hex}"
            uow.plans.create(
                self._ports.plan_factory(
                    plan_id=plan_id,
                    workflow_id=event.workflow_id,
                    turn_id=event.root_turn_id,
                    parent_plan_id=event.previous_plan_id,
                    current_task_id=None,
                    status=PlanStatus.PLANNING.value,
                    revision=event.next_revision,
                    failure_code=None,
                    failure_reason=None,
                )
            )
            record_inbox_once(
                uow,
                inbox_event_factory=self._ports.inbox_event_factory,
                consumer_name=self.CONSUMER_NAME,
                event_id=event.event_id,
            )
            uow.commit()
            return plan_id, event.next_revision
