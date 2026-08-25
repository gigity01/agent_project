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
    """处理用户会话消息的核心用例。

    编排主流程：
    1. 澄清回复分支：若携带 `source_turn_id`，将用户补充信息写入源 Turn，标记澄清为已回答，发布 Replan 异步事件。
    2. 普通消息分支：
       - Context Selection：通过 Context Agent 或规则判定当前消息所关联的历史链（Read Set）并持久化 Turn。
       - Run Planning：多阶段运行 Planner（Evidence 收集 -> Gap 分析 -> Commit 计划生成）。
       - 结果分派：根据 Plan 状态（processing / needs_clarification / unsupported / retry_pending）确定性回写或返回。
    """

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
        """执行发送会话消息用例。

        Args:
            command: 发送消息命令，包含会话 ID、用户消息内容及可选的澄清源 Turn ID。

        Returns:
            SendConversationMessageResult: 包含会话 ID、Turn ID、Plan ID、状态及上下文选择元数据。
        """
        # 分支 1：处理针对已有澄清请求的回复
        if command.source_turn_id is not None:
            plan_id = await asyncio.to_thread(
                self._answer_clarification.execute,
                conversation_id=command.conversation_id,
                source_turn_id=command.source_turn_id,
                answer=command.message,
            )

            return SendConversationMessageResult(
                conversation_id=command.conversation_id,
                turn_id=command.source_turn_id,
                plan_id=plan_id,
                status="retry_pending",
            )

        # 分支 2：普通完整用户消息，执行上下文路由选择
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

        # 执行 Planner 规划（Evidence -> Gap -> Commit）
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
