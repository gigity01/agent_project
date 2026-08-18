"""Planner GapHandler 决策、补查上限与 Application 路由测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest import mock

from agents import ModelSettings
from agents.items import ToolCallItem, ToolCallOutputItem
from pydantic import ValidationError

from app.agent_runtime.business_docs import (
    SearchBusinessDocsInput,
    search_business_docs_handler,
)
from app.agent_runtime.tool_registry import (
    FindEvidenceToolsInput,
    ListEvidenceToolsInput,
    find_evidence_tools_handler,
    list_evidence_tools_handler,
)
from app.agents.collectors import (
    CollectorResult,
    EvidenceItem,
    build_collector_agents,
)
from app.agents.gap_handler import (
    GAP_HANDLER_INSTRUCTIONS,
    GapAction,
    GapDecision,
    GapDecisionError,
)
from app.agents.planner import (
    ClarificationAgentOutput,
    build_planner_agent,
)
from app.modules.planning.application.dto import (
    PlannerContextInput,
    RunPlanningInput,
)
from app.modules.planning.application.errors import PlanningRetryRequested
from app.modules.planning.application.run_planning import RunPlanningUseCase


class _RunResult:
    def __init__(
        self,
        *,
        new_items=None,
        final_output=None,
        history=None,
    ) -> None:
        self.new_items = list(new_items or [])
        self.final_output = final_output
        self._history = list(history or [])

    def to_input_list(self):
        return self._history


class GapHandlerRunnerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        collectors = build_collector_agents(
            model="test-model",
            model_settings=ModelSettings(),
        )
        self.runner = build_planner_agent(
            model="test-model",
            model_settings=ModelSettings(),
            collectors=collectors,
        )
        self.planner_input = PlannerContextInput(
            current_user_input="索引文档 7",
            context_chains=[],
        )

    @staticmethod
    def _evidence_item(
        *,
        outcome="succeeded",
        retryable=False,
        payload=None,
    ) -> EvidenceItem:
        return EvidenceItem(
            tool_name="get_document_chunk_statistics",
            tool_call_id="inner-call",
            arguments={"document_id": 7},
            outcome=outcome,
            result_code="chunk_statistics_result",
            message="查询完成",
            retryable=retryable,
            resource_refs=["document:7"],
            payload=payload or {},
        )

    def _collector_result(
        self,
        *,
        gaps=None,
        evidence_items=None,
        summary="文档证据已检查",
    ) -> CollectorResult:
        return CollectorResult(
            collector_code="document_collector",
            summary=summary,
            gaps=list(gaps or []),
            resource_refs=["document:7"],
            evidence_items=list(evidence_items or []),
        )

    def _evidence_run(
        self,
        collector_result: CollectorResult,
        *,
        history_label: str,
    ) -> _RunResult:
        call_id = f"outer-{history_label}"
        call = ToolCallItem(
            agent=self.runner.evidence_agent,
            raw_item={
                "type": "function_call",
                "call_id": call_id,
                "name": "collect_document_information",
                "arguments": "{}",
            },
        )
        output = ToolCallOutputItem(
            agent=self.runner.evidence_agent,
            raw_item={
                "type": "function_call_output",
                "call_id": call_id,
                "output": "serialized-output",
            },
            output=collector_result.model_dump_json(),
        )
        return _RunResult(
            new_items=[call, output],
            history=[{"role": "user", "content": history_label}],
        )

    @staticmethod
    def _gap_run(decision: GapDecision) -> _RunResult:
        return _RunResult(final_output=decision)

    @staticmethod
    def _planning_context():
        return SimpleNamespace(
            planning_services=SimpleNamespace(
                mark_plan_unsupported=SimpleNamespace(execute=mock.Mock()),
                mark_plan_needs_clarification=SimpleNamespace(
                    execute=mock.Mock()
                ),
            ),
            plan_id="plan-1",
            conversation_id="conversation-1",
        )

    async def test_no_gap_skips_gap_handler_and_enters_commit(self) -> None:
        evidence = self._evidence_run(
            self._collector_result(
                evidence_items=[
                    self._evidence_item(payload={"chunk_count": 3})
                ]
            ),
            history_label="evidence-1",
        )
        commit = _RunResult(final_output="committed")

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(side_effect=[evidence, commit]),
        ) as run:
            result = await self.runner.run(
                planner_input=self.planner_input,
                context=mock.Mock(),
            )

        self.assertIs(result, commit)
        self.assertEqual(run.await_count, 2)
        self.assertIs(run.await_args_list[1].args[0], self.runner.commit_agent)

    async def test_empty_evidence_is_checked_before_capability_only_commit(
        self,
    ) -> None:
        evidence = _RunResult(
            new_items=[],
            history=[{"role": "user", "content": "evidence-1"}],
        )
        capability_only = self._gap_run(
            GapDecision(
                action=GapAction.COMMIT,
                reason="该请求只需由 Commit 判断执行 Capability 是否存在",
            )
        )
        commit = _RunResult(final_output="unsupported committed")

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(
                side_effect=[evidence, capability_only, commit]
            ),
        ) as run:
            result = await self.runner.run(
                planner_input=PlannerContextInput(
                    current_user_input="给 Slack 发消息",
                    context_chains=[],
                ),
                context=mock.Mock(),
            )

        self.assertIs(result, commit)
        self.assertEqual(run.await_count, 3)
        self.assertIs(
            run.await_args_list[1].args[0],
            self.runner.gap_handler_agent,
        )

    async def test_collect_more_runs_one_targeted_second_round_then_commit(
        self,
    ) -> None:
        first = self._evidence_run(
            self._collector_result(gaps=["无法确认文档 7 的切块状态"]),
            history_label="evidence-1",
        )
        collect_more = self._gap_run(
            GapDecision(
                action=GapAction.COLLECT_MORE,
                reason="Registry 中存在切块统计查询，但第一轮没有调用",
                follow_up="只确认文档 7 当前切块构建状态",
            )
        )
        second = self._evidence_run(
            self._collector_result(
                evidence_items=[
                    self._evidence_item(payload={"chunk_count": 3})
                ]
            ),
            history_label="evidence-2",
        )
        resolved = self._gap_run(
            GapDecision(
                action=GapAction.COMMIT,
                reason="第二轮 Evidence 已确认切块状态",
            )
        )
        commit = _RunResult(final_output="committed")

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(
                side_effect=[first, collect_more, second, resolved, commit]
            ),
        ) as run:
            result = await self.runner.run(
                planner_input=self.planner_input,
                context=mock.Mock(),
            )

        self.assertIs(result, commit)
        self.assertEqual(run.await_count, 5)
        second_evidence_call = run.await_args_list[2]
        self.assertIs(second_evidence_call.args[0], self.runner.evidence_agent)
        self.assertIn(
            "只确认文档 7 当前切块构建状态",
            second_evidence_call.args[1][-1]["content"],
        )
        second_gap_input = json.loads(run.await_args_list[3].args[1])
        self.assertFalse(second_gap_input["collect_more_allowed"])
        self.assertEqual(len(second_gap_input["evidence_rounds"]), 2)

    async def test_retry_requires_retryable_failed_evidence(self) -> None:
        evidence = self._evidence_run(
            self._collector_result(
                gaps=["切块状态仍未知"],
                evidence_items=[
                    self._evidence_item(
                        outcome="failed",
                        retryable=True,
                    )
                ],
            ),
            history_label="evidence-1",
        )
        retry = self._gap_run(
            GapDecision(
                action=GapAction.RETRY,
                reason="正确查询发生可重试故障",
            )
        )

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(side_effect=[evidence, retry]),
        ):
            with self.assertRaisesRegex(
                PlanningRetryRequested,
                "可重试故障",
            ):
                await self.runner.run(
                    planner_input=self.planner_input,
                    context=mock.Mock(),
                )

    async def test_non_retryable_failure_cannot_be_labeled_retry(self) -> None:
        evidence = self._evidence_run(
            self._collector_result(
                gaps=["切块状态仍未知"],
                evidence_items=[
                    self._evidence_item(
                        outcome="failed",
                        retryable=False,
                    )
                ],
            ),
            history_label="evidence-1",
        )
        invalid_retry = self._gap_run(
            GapDecision(
                action=GapAction.RETRY,
                reason="不可重试失败不应进入 RETRY",
            )
        )

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(side_effect=[evidence, invalid_retry]),
        ):
            with self.assertRaisesRegex(
                GapDecisionError,
                "retryable=true",
            ):
                await self.runner.run(
                    planner_input=self.planner_input,
                    context=mock.Mock(),
                )

    async def test_ambiguous_user_reference_uses_existing_clarification_flow(
        self,
    ) -> None:
        evidence = self._evidence_run(
            self._collector_result(
                gaps=["无法唯一确定用户指的是文档 7 还是文档 8"]
            ),
            history_label="evidence-1",
        )
        clarification = self._gap_run(
            GapDecision(
                action=GapAction.CLARIFICATION,
                reason="selected context 中存在两个合理目标",
                clarification_kind="resource",
                required_information=["需要重新处理的 document_id"],
                known_resource_refs=["document:7", "document:8"],
            )
        )
        question = _RunResult(
            final_output=ClarificationAgentOutput(
                question="需要重新处理文档 7 还是文档 8？"
            )
        )
        context = self._planning_context()

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(
                side_effect=[evidence, clarification, question]
            ),
        ) as run:
            result = await self.runner.run(
                planner_input=self.planner_input,
                context=context,
            )

        self.assertIs(result, question)
        marked = context.planning_services.mark_plan_needs_clarification.execute
        marked.assert_called_once()
        self.assertEqual(marked.call_args.args[0].plan_id, "plan-1")
        self.assertIs(
            run.await_args_list[2].args[0],
            self.runner.clarification_agent,
        )

    async def test_unavailable_required_fact_marks_plan_unsupported(
        self,
    ) -> None:
        evidence = self._evidence_run(
            self._collector_result(gaps=["无法取得外部审批状态"]),
            history_label="evidence-1",
        )
        unsupported = self._gap_run(
            GapDecision(
                action=GapAction.UNSUPPORTED,
                reason="Registry 没有外部审批状态查询能力",
            )
        )
        context = self._planning_context()

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(side_effect=[evidence, unsupported]),
        ) as run:
            result = await self.runner.run(
                planner_input=self.planner_input,
                context=context,
            )

        self.assertIs(result, unsupported)
        self.assertEqual(run.await_count, 2)
        marked = context.planning_services.mark_plan_unsupported.execute
        marked.assert_called_once()
        self.assertIn("外部审批", marked.call_args.args[0].reason)

    async def test_non_blocking_gap_can_enter_commit(self) -> None:
        evidence = self._evidence_run(
            self._collector_result(gaps=["无法确认首次索引时间"]),
            history_label="evidence-1",
        )
        non_blocking = self._gap_run(
            GapDecision(
                action=GapAction.COMMIT,
                reason="首次索引时间与重新处理文档无关",
            )
        )
        commit = _RunResult(final_output="committed")

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(
                side_effect=[evidence, non_blocking, commit]
            ),
        ) as run:
            result = await self.runner.run(
                planner_input=self.planner_input,
                context=mock.Mock(),
            )

        self.assertIs(result, commit)
        commit_history = run.await_args_list[2].args[1]
        self.assertIn("Gap Decision", commit_history[-1]["content"])

    async def test_second_round_cannot_request_third_collection(self) -> None:
        first = self._evidence_run(
            self._collector_result(gaps=["切块状态未知"]),
            history_label="evidence-1",
        )
        collect_more = self._gap_run(
            GapDecision(
                action=GapAction.COLLECT_MORE,
                reason="第一轮漏查",
                follow_up="确认切块状态",
            )
        )
        second = self._evidence_run(
            self._collector_result(gaps=["切块状态仍未知"]),
            history_label="evidence-2",
        )
        collect_again = self._gap_run(
            GapDecision(
                action=GapAction.COLLECT_MORE,
                reason="仍想补查",
                follow_up="再次确认切块状态",
            )
        )

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(
                side_effect=[first, collect_more, second, collect_again]
            ),
        ) as run:
            with self.assertRaisesRegex(
                GapDecisionError,
                "禁止再次 COLLECT_MORE",
            ):
                await self.runner.run(
                    planner_input=self.planner_input,
                    context=mock.Mock(),
                )

        self.assertEqual(run.await_count, 4)

    async def test_successful_empty_business_result_is_evidence_not_gap(
        self,
    ) -> None:
        evidence = self._evidence_run(
            self._collector_result(
                evidence_items=[
                    self._evidence_item(payload={"document": None})
                ],
                gaps=[],
            ),
            history_label="evidence-1",
        )
        commit = _RunResult(final_output="committed")

        with mock.patch(
            "app.agents.planner.Runner.run",
            new=mock.AsyncMock(side_effect=[evidence, commit]),
        ) as run:
            await self.runner.run(
                planner_input=self.planner_input,
                context=mock.Mock(),
            )

        self.assertEqual(run.await_count, 2)
        self.assertIs(run.await_args_list[1].args[0], self.runner.commit_agent)


class GapKnowledgeToolsTest(unittest.TestCase):
    def test_business_docs_and_registry_resolve_chunk_query_path(self) -> None:
        docs = search_business_docs_handler(
            SearchBusinessDocsInput(query="如何确认 Document 的 chunk 状态")
        )
        registry = find_evidence_tools_handler(
            FindEvidenceToolsInput(query="文档切块状态统计")
        )

        self.assertTrue(docs.matches)
        self.assertIn(
            "get_document_chunk_statistics",
            {
                tool.descriptor.name
                for tool in registry.tools
            },
        )

    def test_registry_is_dynamic_read_only_authority(self) -> None:
        registry = list_evidence_tools_handler(ListEvidenceToolsInput())

        self.assertTrue(registry.tools)
        self.assertTrue(
            all(
                tool.descriptor.operation_type == "query"
                and not tool.descriptor.side_effect
                for tool in registry.tools
            )
        )
        self.assertEqual(
            find_evidence_tools_handler(
                FindEvidenceToolsInput(
                    query="get_external_approval_status"
                )
            ).tools,
            [],
        )
        self.assertIn("Tool Registry 优先", GAP_HANDLER_INSTRUCTIONS)
        self.assertIn("不得扩大 Read Set", GAP_HANDLER_INSTRUCTIONS)

    def test_business_docs_do_not_return_weakly_related_sections(self) -> None:
        result = search_business_docs_handler(
            SearchBusinessDocsInput(query="外星天气发票审批")
        )

        self.assertEqual(result.matches, [])

    def test_registry_wins_when_documented_query_tool_is_missing(self) -> None:
        docs = search_business_docs_handler(
            SearchBusinessDocsInput(query="如何确认 Document 的 chunk 状态")
        )
        self.assertTrue(
            any(
                "get_document_chunk_statistics" in match.content
                for match in docs.matches
            )
        )

        with mock.patch(
            "app.agent_runtime.tool_registry.list_evidence_tool_views",
            return_value=(),
        ):
            registry = find_evidence_tools_handler(
                FindEvidenceToolsInput(query="get_document_chunk_statistics")
            )

        self.assertEqual(registry.tools, [])
        self.assertIn("Tool Registry 优先", GAP_HANDLER_INSTRUCTIONS)

    def test_gap_decision_requires_action_specific_fields(self) -> None:
        with self.assertRaises(ValidationError):
            GapDecision(
                action=GapAction.COLLECT_MORE,
                reason="需要补查",
            )
        with self.assertRaises(ValidationError):
            GapDecision(
                action=GapAction.CLARIFICATION,
                reason="用户指代不明",
            )
        with self.assertRaises(ValidationError):
            GapDecision(
                action=GapAction.COMMIT,
                reason="缺口不阻塞",
                known_resource_refs=["document:7"],
            )


class PlanningRetryRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_retry_decision_is_persisted_by_planning_application(self) -> None:
        runner = SimpleNamespace(
            run=mock.AsyncMock(
                side_effect=PlanningRetryRequested("Evidence 查询临时失败")
            )
        )
        use_case = RunPlanningUseCase(
            ports=mock.Mock(),
            planning_use_cases=mock.Mock(),
            planner_runner=runner,
            document_services=mock.Mock(),
            context_services=mock.Mock(),
            context_resource_service=mock.Mock(),
            context_chain_mapper=mock.Mock(),
            operations_services=mock.Mock(),
        )
        use_case._build_agent_context = mock.Mock(return_value=mock.Mock())
        expected = mock.sentinel.planning_result
        use_case._finish_from_database = mock.Mock(return_value=expected)

        result = await use_case._run_existing_plan(
            RunPlanningInput(
                conversation_id="conversation-1",
                turn_id="turn-1",
            ),
            "plan-1",
            PlannerContextInput(
                current_user_input="索引文档 7",
                context_chains=[],
            ),
        )

        self.assertIs(result, expected)
        use_case._finish_from_database.assert_called_once_with(
            "plan-1",
            "turn-1",
            "Evidence 查询临时失败",
        )


if __name__ == "__main__":
    unittest.main()
