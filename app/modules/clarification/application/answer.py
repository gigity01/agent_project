"""把回答写回源 Turn，并可靠请求同一 Turn 的新 Plan revision。"""

from datetime import datetime
from uuid import uuid4

from app.modules.clarification.application.errors import (
    ClarificationApplicationError,
)
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
        source_turn_id: str,
        answer: str,
    ) -> str:
        normalized_answer = answer.strip()
        if not normalized_answer:
            raise ClarificationApplicationError(
                400,
                "Clarification 回答不能为空",
            )

        with self._uow_factory() as uow:
            request = uow.clarifications.get_by_source_turn_id_for_update(
                source_turn_id
            )
            if request is None:
                raise ClarificationApplicationError(
                    404,
                    "Clarification 不存在",
                )
            source_turn = uow.conversation_turns.get_by_id_for_update(
                source_turn_id
            )
            plan = uow.plans.get_by_id_for_update(request.source_plan_id)
            if source_turn is None or plan is None:
                raise ClarificationApplicationError(
                    409,
                    "Clarification 关联状态不完整",
                )
            if (
                source_turn.conversation_id != conversation_id
                or request.conversation_id != conversation_id
            ):
                raise ClarificationApplicationError(
                    404,
                    "Clarification 不存在",
                )
            if (
                plan.turn_id != source_turn_id
                or request.status != ClarificationStatus.OPEN.value
                or source_turn.status
                != ContextTurnStatus.NEEDS_CLARIFICATION.value
                or plan.status != PlanStatus.NEEDS_CLARIFICATION.value
            ):
                raise ClarificationApplicationError(
                    409,
                    "Clarification 当前状态不允许回答",
                )

            if source_turn.clarification_input is not None:
                raise ClarificationApplicationError(
                    409,
                    "Clarification 已澄清",
                )

            request.status = ClarificationStatus.ANSWERED.value
            request.answer_turn_id = source_turn_id
            source_turn.clarification_input = normalized_answer
            uow.conversation_turns.set_status(
                source_turn,
                ContextTurnStatus.PROCESSING.value,
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
                        "root_turn_id": source_turn_id,
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
