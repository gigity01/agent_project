"""把新 Turn 关联到 open Clarification 并可靠请求 Replan。"""

from datetime import datetime
from uuid import uuid4

from app.modules.clarification.domain.enums import ClarificationStatus
from app.modules.context.domain.enums import ContextTurnStatus
from app.modules.messaging.domain.enums import (
    OutboxEventStatus,
    RuntimeEventType,
)
from app.modules.planning.domain.enums import PlanStatus


class AnswerClarificationUseCase:
    def __init__(
        self,
        *,
        uow_factory,
        outbox_event_factory,
    ) -> None:
        self._uow_factory = uow_factory
        self._outbox_event_factory = outbox_event_factory

    def execute(
        self,
        *,
        conversation_id: str,
        answer_turn_id: str,
    ) -> str | None:
        with self._uow_factory() as uow:
            request = uow.clarifications.get_open_for_conversation_for_update(
                conversation_id
            )
            if request is None:
                return None
            answer_turn = uow.conversation_turns.get_by_id_for_update(
                answer_turn_id
            )
            plan = uow.plans.get_by_id_for_update(request.source_plan_id)
            if answer_turn is None or plan is None:
                raise RuntimeError("Clarification 关联状态不存在")
            if (
                answer_turn.conversation_id != conversation_id
                or answer_turn.status != ContextTurnStatus.ROUTED.value
                or plan.status != PlanStatus.NEEDS_CLARIFICATION.value
            ):
                raise RuntimeError("Clarification 当前状态不允许回答")
            request.status = ClarificationStatus.ANSWERED.value
            request.answer_turn_id = answer_turn_id
            uow.conversation_turns.set_status(
                answer_turn, ContextTurnStatus.PROCESSING.value
            )
            uow.outbox.add(
                self._outbox_event_factory(
                    event_id=f"event_{uuid4().hex}",
                    event_type=RuntimeEventType.REPLAN_REQUESTED.value,
                    aggregate_type="plan",
                    aggregate_id=plan.plan_id,
                    payload_json={
                        "workflow_id": plan.workflow_id,
                        "conversation_id": conversation_id,
                        "root_turn_id": answer_turn_id,
                        "previous_plan_id": plan.plan_id,
                        "next_revision": plan.revision + 1,
                        "trigger_type": "clarification_answered",
                        "source_task_id": None,
                        "error_code": None,
                        "error_message": None,
                    },
                    status=OutboxEventStatus.PENDING.value,
                    attempts=0,
                    available_at=datetime.now(),
                    published_at=None,
                )
            )
            uow.commit()
            return plan.plan_id
