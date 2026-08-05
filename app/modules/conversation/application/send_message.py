"""Context → Planning → 状态分派的用户消息主链路。"""

from __future__ import annotations

import asyncio

from app.modules.context.application.dto import (
    CompleteTurnCommand,
    SendMessageCommand,
)
from app.modules.conversation.application.dto import (
    RoutingMetadata,
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
        routed = await self._context_service.send_message(
            SendMessageCommand(
                conversation_id=command.conversation_id,
                message=command.message,
            )
        )
        routing = RoutingMetadata(
            route_mode=routed.decision.route_mode,
            selected_chain_ids=list(routed.decision.selected_chain_ids),
            new_chain_id=routed.new_chain_id,
            reason_summary=routed.decision.reason_summary,
        )
        clarification_plan_id = await asyncio.to_thread(
            self._answer_clarification.execute,
            conversation_id=command.conversation_id,
            answer_turn_id=routed.turn_id,
        )
        if clarification_plan_id is not None:
            return SendConversationMessageResult(
                conversation_id=command.conversation_id,
                turn_id=routed.turn_id,
                plan_id=clarification_plan_id,
                status="retry_pending",
                routing=routing,
            )

        planning = await self._run_planning.execute(
            RunPlanningInput(
                conversation_id=routed.conversation_id,
                turn_id=routed.turn_id,
                revision=1,
            )
        )
        if planning.status == PlanStatus.READY:
            return SendConversationMessageResult(
                conversation_id=routed.conversation_id,
                turn_id=routed.turn_id,
                plan_id=planning.plan_id,
                status="processing",
                task_ids=planning.task_ids,
                routing=routing,
            )
        if planning.status == PlanStatus.UNSUPPORTED:
            message = planning.failure_reason or "当前业务暂不支持该请求。"
            await self._context_service.complete_turn(
                routed.turn_id,
                CompleteTurnCommand(
                    assistant_content=message,
                    assistant_compact=message,
                    task_ids=[],
                    task_result_summary=message,
                ),
            )
            return SendConversationMessageResult(
                conversation_id=routed.conversation_id,
                turn_id=routed.turn_id,
                plan_id=planning.plan_id,
                status="unsupported",
                assistant_message=message,
                routing=routing,
            )
        if planning.status == PlanStatus.NEEDS_CLARIFICATION:
            question = planning.clarification_question
            if not question:
                raise RuntimeError("Clarification Agent 未生成问题")
            await self._context_service.complete_turn(
                routed.turn_id,
                CompleteTurnCommand(
                    assistant_content=question,
                    assistant_compact=question,
                    task_ids=[],
                    task_result_summary="等待用户补充信息",
                ),
            )
            return SendConversationMessageResult(
                conversation_id=routed.conversation_id,
                turn_id=routed.turn_id,
                plan_id=planning.plan_id,
                status="needs_clarification",
                assistant_message=question,
                routing=routing,
            )
        if planning.status == PlanStatus.RETRY_PENDING:
            return SendConversationMessageResult(
                conversation_id=routed.conversation_id,
                turn_id=routed.turn_id,
                plan_id=planning.plan_id,
                status="retry_pending",
                routing=routing,
            )
        return SendConversationMessageResult(
            conversation_id=routed.conversation_id,
            turn_id=routed.turn_id,
            plan_id=planning.plan_id,
            status="failed",
            assistant_message=planning.failure_reason,
            routing=routing,
        )
