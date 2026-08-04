"""Collector Agent 的 Catalog 隔离与 Agent-as-Tool 包装测试。"""

from __future__ import annotations

import unittest

from agents import ModelSettings

from app.agents.collectors import (
    CollectorRequest,
    CollectorResult,
    build_collector_agents,
)


class CollectorAgentsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.collectors = build_collector_agents(
            model="test-model",
            model_settings=ModelSettings(),
        )

    def test_collectors_have_only_role_specific_read_tools(self) -> None:
        document_tools = {
            tool.name for tool in self.collectors.document.tools
        }
        context_tools = {tool.name for tool in self.collectors.context.tools}
        operations_tools = {
            tool.name for tool in self.collectors.operations.tools
        }

        self.assertIn("get_document", document_tools)
        self.assertNotIn("process_document", document_tools)
        self.assertEqual(
            context_tools,
            {
                "get_conversation_turn",
                "list_conversation_turns",
                "get_context_chain",
                "list_context_chains",
                "list_context_chain_nodes",
                "list_context_chain_resources",
                "list_context_route_records",
            },
        )
        self.assertIn("query_document_log_events", operations_tools)
        self.assertIn("get_document_operation_timeline", operations_tools)
        self.assertIn("get_document_workflow_timeline", operations_tools)
        self.assertIn("query_agent_tool_audits", operations_tools)

    def test_collectors_are_structured_and_have_no_handoffs(self) -> None:
        for agent in (
            self.collectors.document,
            self.collectors.context,
            self.collectors.operations,
        ):
            self.assertIs(agent.output_type, CollectorResult)
            self.assertEqual(agent.handoffs, [])

    def test_planner_receives_three_agent_as_tools(self) -> None:
        tools = self.collectors.planner_tools

        self.assertEqual(
            {tool.name for tool in tools},
            {
                "collect_document_information",
                "collect_context_information",
                "collect_operation_information",
            },
        )
        self.assertTrue(all(tool._is_agent_tool for tool in tools))
        self.assertTrue(all(tool.needs_approval is False for tool in tools))
        self.assertTrue(
            all(
                tool.params_json_schema["properties"].get("question")
                for tool in tools
            )
        )

    def test_collector_request_keeps_planner_scope_structured(self) -> None:
        request = CollectorRequest(
            question="检查文档 7 的失败原因",
            conversation_id="conversation-1",
            document_ids=[7],
            workflow_ids=["workflow-1"],
        )

        self.assertEqual(request.document_ids, [7])
        self.assertEqual(request.workflow_ids, ["workflow-1"])


if __name__ == "__main__":
    unittest.main()
