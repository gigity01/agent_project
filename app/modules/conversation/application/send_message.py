"""Context → Planning → 状态分派的用户消息主链路。"""

from __future__ import annotations

import asyncio

from app.modules.context.application.dto import (
    CompleteTurnCommand,
    SendMessageCommand,
)
from app.modules.context.application.attribution_policy import (
    build_read_set_fallback_attribution,
)
from app.modules.context.domain.selection_policy import (
    derive_context_selection_mode,
)
from app.modules.conversation.application.dto import (
    ContextSelectionMetadata,
    SendConversationMessageCommand,
    SendConversationMessageResult,
)
from app.modules.planning.application.dto import RunPlanningInput
from app.modules.planning.domain.enums import PlanStatus


class SendConversationMessageUseCase:
    def __init__(
        self,
        *,
        context_service,
        run_planning,
        answer_clarification,
    ) -> None:
        self._context_service = context_service
        self._run_planning = run_planning
        self._answer_clarification = answer_clarification

    async def execute(
        self,
        command: SendConversationMessageCommand,
    ) -> SendConversationMessageResult:
        selection = await self._context_service.send_message(
            SendMessageCommand(
                conversation_id=command.conversation_id,
                message=command.message,
            )
        )
        selection_metadata = ContextSelectionMetadata(
            selection_mode=derive_context_selection_mode(
                selection.decision.relevant_chain_ids
            ),
            relevant_chain_ids=list(
                selection.decision.relevant_chain_ids
            ),
            reason_summary=selection.decision.reason_summary,
        )
        fallback_attribution = build_read_set_fallback_attribution(
            selection.decision.relevant_chain_ids
        )
        clarification_plan_id = await asyncio.to_thread(
            self._answer_clarification.execute,
            conversation_id=command.conversation_id,
            answer_turn_id=selection.turn_id,
        )
        if clarification_plan_id is not None:
            return SendConversationMessageResult(
                conversation_id=command.conversation_id,
                turn_id=selection.turn_id,
                plan_id=clarification_plan_id,
                status="retry_pending",
                context_selection=selection_metadata,
            )

        planning = await self._run_planning.execute(
            RunPlanningInput(
                conversation_id=selection.conversation_id,
                turn_id=selection.turn_id,
                revision=1,
            )
        )
        if planning.status == PlanStatus.READY:
            return SendConversationMessageResult(
                conversation_id=selection.conversation_id,
                turn_id=selection.turn_id,
                plan_id=planning.plan_id,
                status="processing",
                task_ids=planning.task_ids,
                context_selection=selection_metadata,
            )
        if planning.status == PlanStatus.UNSUPPORTED:
            message = planning.failure_reason or "当前业务暂不支持该请求。"
            await self._context_service.complete_turn(
                selection.turn_id,
                CompleteTurnCommand(
                    assistant_content=message,
                    assistant_compact=message,
                    task_ids=[],
                    task_result_summary=message,
                    attribution=fallback_attribution,
                ),
            )
            return SendConversationMessageResult(
                conversation_id=selection.conversation_id,
                turn_id=selection.turn_id,
                plan_id=planning.plan_id,
                status="unsupported",
                assistant_message=message,
                context_selection=selection_metadata,
            )
        if planning.status == PlanStatus.NEEDS_CLARIFICATION:
            question = planning.clarification_question
            if not question:
                raise RuntimeError("Clarification Agent 未生成问题")
            await self._context_service.complete_turn(
                selection.turn_id,
                CompleteTurnCommand(
                    assistant_content=question,
                    assistant_compact=question,
                    task_ids=[],
                    task_result_summary="等待用户补充信息",
                    attribution=fallback_attribution,
                ),
            )
            return SendConversationMessageResult(
                conversation_id=selection.conversation_id,
                turn_id=selection.turn_id,
                plan_id=planning.plan_id,
                status="needs_clarification",
                assistant_message=question,
                context_selection=selection_metadata,
            )
        if planning.status == PlanStatus.RETRY_PENDING:
            return SendConversationMessageResult(
                conversation_id=selection.conversation_id,
                turn_id=selection.turn_id,
                plan_id=planning.plan_id,
                status="retry_pending",
                context_selection=selection_metadata,
            )
        return SendConversationMessageResult(
            conversation_id=selection.conversation_id,
            turn_id=selection.turn_id,
            plan_id=planning.plan_id,
            status="failed",
            assistant_message=planning.failure_reason,
            context_selection=selection_metadata,
        )
