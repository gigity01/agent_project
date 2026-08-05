"""读取 Turn 与最新 Plan 的状态事实。"""

from app.modules.conversation.application.dto import TurnStatusResult


class GetTurnStatusUseCase:
    def __init__(self, uow_factory) -> None:
        self._uow_factory = uow_factory

    def execute(self, conversation_id: str, turn_id: str) -> TurnStatusResult:
        with self._uow_factory() as uow:
            turn = uow.conversation_turns.get_by_id(turn_id)
            if turn is None or turn.conversation_id != conversation_id:
                raise ValueError("Conversation Turn 不存在")
            plan = uow.plans.get_latest_by_turn(turn_id)
            return TurnStatusResult(
                conversation_id=conversation_id,
                turn_id=turn_id,
                turn_status=turn.status,
                plan_id=None if plan is None else plan.plan_id,
                plan_status=None if plan is None else plan.status,
                revision=None if plan is None else plan.revision,
                task_ids=list(turn.task_ids or []),
                assistant_message=turn.assistant_content,
            )
