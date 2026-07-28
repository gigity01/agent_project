"""Context Agent strict tool Schema 与响应解析测试。"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from app.agents.context_agent import (
    CONTEXT_ROUTE_TOOL_NAME,
    ContextAgentOutputError,
    ContextAgentRouter,
    build_context_route_tool_schema,
)
from app.schemas.context import (
    ContextAgentInput,
    ContextRouteMode,
)


class ContextRouteToolSchemaTest(unittest.TestCase):
    def test_schema_is_generated_from_pydantic_without_local_refs(self) -> None:
        schema = build_context_route_tool_schema()

        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {
                "selected_chain_ids",
                "create_new_chain",
                "route_mode",
                "reason_summary",
            },
        )
        self.assertNotIn("$defs", schema)
        self.assertNotIn("$ref", json.dumps(schema))
        self.assertEqual(
            schema["properties"]["route_mode"]["enum"],
            [mode.value for mode in ContextRouteMode],
        )


class ContextAgentRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_forces_one_strict_tool_and_parses_arguments(self) -> None:
        create = mock.AsyncMock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            tool_calls=[
                                SimpleNamespace(
                                    function=SimpleNamespace(
                                        name=CONTEXT_ROUTE_TOOL_NAME,
                                        arguments=json.dumps(
                                            {
                                                "selected_chain_ids": [],
                                                "create_new_chain": True,
                                                "route_mode": "new_chain",
                                                "reason_summary": "当前没有相关已有链。",
                                            },
                                            ensure_ascii=False,
                                        ),
                                    )
                                )
                            ]
                        )
                    )
                ]
            )
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        )
        provider = SimpleNamespace(
            strict_tool_client=client,
            model_name="deepseek-v4-flash",
        )
        router = ContextAgentRouter(provider)

        decision = await router.route(
            ContextAgentInput(
                conversation_id="conversation-1",
                current_turn_id="turn-1",
                current_user_input="创建新的日志告警模块。",
                chains=[],
            )
        )

        self.assertEqual(decision.route_mode, ContextRouteMode.NEW_CHAIN)
        self.assertTrue(decision.create_new_chain)
        request = create.await_args.kwargs
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(
            request["tool_choice"]["function"]["name"],
            CONTEXT_ROUTE_TOOL_NAME,
        )
        self.assertFalse(request["parallel_tool_calls"])
        function = request["tools"][0]["function"]
        self.assertTrue(function["strict"])
        self.assertEqual(function["parameters"]["type"], "object")
        self.assertFalse(function["parameters"]["additionalProperties"])

    async def test_rejects_non_contract_tool_arguments(self) -> None:
        create = mock.AsyncMock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            tool_calls=[
                                SimpleNamespace(
                                    function=SimpleNamespace(
                                        name=CONTEXT_ROUTE_TOOL_NAME,
                                        arguments=json.dumps(
                                            {
                                                "selected_chain_ids": [],
                                                "create_new_chain": True,
                                                "route_mode": "new_chain",
                                                "reason_summary": "新链。",
                                                "unexpected": "not allowed",
                                            }
                                        ),
                                    )
                                )
                            ]
                        )
                    )
                ]
            )
        )
        provider = SimpleNamespace(
            strict_tool_client=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=create)
                )
            ),
            model_name="deepseek-v4-flash",
        )
        router = ContextAgentRouter(provider)

        with self.assertRaises(ContextAgentOutputError):
            await router.route(
                ContextAgentInput(
                    conversation_id="conversation-1",
                    current_turn_id="turn-1",
                    current_user_input="创建新链。",
                    chains=[],
                )
            )


if __name__ == "__main__":
    unittest.main()
