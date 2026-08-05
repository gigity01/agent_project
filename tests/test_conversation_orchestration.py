"""Conversation Coordinator 的 Planning 状态分派测试。"""

from __future__ import annotations

import unittest
from unittest import mock

from app.modules.context.application.dto import RouteContextResult
from app.modules.context.domain.enums import ContextRouteMode
from app.modules.context.domain.models import ContextRouteDecision
from app.modules.conversation.application.dto import (
    SendConversationMessageCommand,
)
from app.modules.conversation.application.send_message import (
    SendConversationMessageUseCase,
)
from app.modules.planning.application.dto import RunPlanningResult
from app.modules.planning.domain.enums import PlanStatus


def _routed() -> RouteContextResult:
    return RouteContextResult(
        conversation_id="conversation-1",
        turn_id="turn-1",
        message="处理文档 7",
        selected_chains=[],
        new_chain_id="chain-1",
        decision=ContextRouteDecision(
            selected_chain_ids=[],
            create_new_chain=True,
            route_mode=ContextRouteMode.NEW_CHAIN,
            reason_summary="新业务链",
        ),
    )


class ConversationOrchestrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.context = mock.Mock()
        self.context.send_message = mock.AsyncMock(return_value=_routed())
        self.context.complete_turn = mock.AsyncMock()
        self.planning = mock.Mock()
        self.planning.execute = mock.AsyncMock()
        self.answer = mock.Mock()
        self.answer.execute.return_value = None
        self.use_case = SendConversationMessageUseCase(
            context_service=self.context,
            run_planning=self.planning,
            answer_clarification=self.answer,
        )

    async def test_ready_returns_processing_without_running_tasks_inline(self) -> None:
        self.planning.execute.return_value = RunPlanningResult(
            plan_id="plan-1",
            turn_id="turn-1",
            status=PlanStatus.READY,
            task_ids=["task-1"],
            failure_reason=None,
        )
        result = await self.use_case.execute(
            SendConversationMessageCommand(
                conversation_id="conversation-1",
                message="处理文档 7",
            )
        )
        self.assertEqual(result.status, "processing")
        self.assertEqual(result.task_ids, ["task-1"])
        self.context.complete_turn.assert_not_awaited()

    async def test_unsupported_completes_current_turn(self) -> None:
        self.planning.execute.return_value = RunPlanningResult(
            plan_id="plan-unsupported",
            turn_id="turn-1",
            status=PlanStatus.UNSUPPORTED,
            task_ids=[],
            failure_reason="当前能力不支持",
        )
        result = await self.use_case.execute(
            SendConversationMessageCommand(
                conversation_id="conversation-1",
                message="执行未支持操作",
            )
        )
        self.assertEqual(result.status, "unsupported")
        command = self.context.complete_turn.await_args.args[1]
        self.assertEqual(command.assistant_content, "当前能力不支持")

    async def test_clarification_question_completes_source_turn(self) -> None:
        self.planning.execute.return_value = RunPlanningResult(
            plan_id="plan-question",
            turn_id="turn-1",
            status=PlanStatus.NEEDS_CLARIFICATION,
            task_ids=[],
            failure_reason="文档不唯一",
            clarification_question="请确认要处理哪一个文档？",
        )
        result = await self.use_case.execute(
            SendConversationMessageCommand(
                conversation_id="conversation-1",
                message="处理那个文档",
            )
        )
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(
            result.assistant_message,
            "请确认要处理哪一个文档？",
        )
        command = self.context.complete_turn.await_args.args[1]
        self.assertEqual(command.task_ids, [])


if __name__ == "__main__":
    unittest.main()
