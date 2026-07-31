"""Context Agent strict tool Schema、确定性分支与响应解析测试。"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import mock

from app.modules.context.infrastructure.llm.deepseek_router import (
    CONTEXT_ROUTE_TOOL_NAME,
    DeepSeekContextRouter,
)
from app.modules.context.infrastructure.llm.strict_schema_adapter import (
    ContextAgentOutputError,
    build_context_route_tool_schema,
)
from app.schemas.context import (
    ContextAgentInput,
    ContextChain,
    ContextResourceQueue,
    ContextRouteMode,
)


ContextAgentRouter = DeepSeekContextRouter


def _existing_chain() -> ContextChain:
    return ContextChain(
        chain_id="chain-1",
        conversation_id="conversation-1",
        nodes=[],
        resource_queue=ContextResourceQueue(capacity=16, items=[]),
        last_active_at=datetime(2026, 7, 28, tzinfo=UTC),
        archived=False,
    )


def _agent_input(*, with_chain: bool = True) -> ContextAgentInput:
    return ContextAgentInput(
        conversation_id="conversation-1",
        current_turn_id="turn-1",
        current_user_input="继续处理之前的文档方案。",
        chains=[_existing_chain()] if with_chain else [],
    )


def _tool_response(arguments: dict[str, object]):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name=CONTEXT_ROUTE_TOOL_NAME,
                                arguments=json.dumps(
                                    arguments,
                                    ensure_ascii=False,
                                ),
                            )
                        )
                    ]
                )
            )
        ]
    )


def _invalid_response():
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(tool_calls=[])
            )
        ]
    )


def _provider(create: mock.AsyncMock):
    return SimpleNamespace(
        strict_tool_client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        ),
        model_name="deepseek-v4-flash",
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
        serialized = json.dumps(schema)
        self.assertNotIn("$defs", schema)
        self.assertNotIn("$ref", serialized)
        self.assertNotIn("minLength", serialized)
        self.assertNotIn("maxLength", serialized)
        self.assertEqual(
            schema["properties"]["route_mode"]["enum"],
            [mode.value for mode in ContextRouteMode],
        )


class ContextAgentRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_without_existing_chains_returns_new_chain_without_llm(self) -> None:
        create = mock.AsyncMock()
        router = ContextAgentRouter(_provider(create))

        decision = await router.route(_agent_input(with_chain=False))

        self.assertEqual(decision.route_mode, ContextRouteMode.NEW_CHAIN)
        self.assertTrue(decision.create_new_chain)
        self.assertEqual(decision.selected_chain_ids, [])
        create.assert_not_awaited()

    async def test_forces_one_strict_tool_and_parses_arguments(self) -> None:
        create = mock.AsyncMock(
            return_value=_tool_response(
                {
                    "selected_chain_ids": ["chain-1"],
                    "create_new_chain": False,
                    "route_mode": "single_match",
                    "reason_summary": "当前输入延续已有文档方案。",
                }
            )
        )
        router = ContextAgentRouter(_provider(create))

        decision = await router.route(_agent_input())

        self.assertEqual(decision.route_mode, ContextRouteMode.SINGLE_MATCH)
        self.assertEqual(decision.selected_chain_ids, ["chain-1"])
        request = create.await_args.kwargs
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(
            request["tool_choice"]["function"]["name"],
            CONTEXT_ROUTE_TOOL_NAME,
        )
        self.assertFalse(request["parallel_tool_calls"])
        self.assertEqual(request["temperature"], 0)
        function = request["tools"][0]["function"]
        self.assertTrue(function["strict"])
        self.assertEqual(function["parameters"]["type"], "object")
        self.assertFalse(function["parameters"]["additionalProperties"])

    async def test_retries_once_after_invalid_tool_response(self) -> None:
        create = mock.AsyncMock(
            side_effect=[
                _invalid_response(),
                _tool_response(
                    {
                        "selected_chain_ids": ["chain-1"],
                        "create_new_chain": False,
                        "route_mode": "single_match",
                        "reason_summary": "第二次返回合法路由。",
                    }
                ),
            ]
        )
        router = ContextAgentRouter(
            _provider(create),
            max_output_attempts=2,
        )

        decision = await router.route(_agent_input())

        self.assertEqual(decision.selected_chain_ids, ["chain-1"])
        self.assertEqual(create.await_count, 2)
        second_request = create.await_args_list[1].kwargs
        self.assertIn(
            "上一次响应未形成唯一且合法",
            second_request["messages"][1]["content"],
        )

    async def test_raises_after_output_attempts_are_exhausted(self) -> None:
        create = mock.AsyncMock(
            side_effect=[_invalid_response(), _invalid_response()]
        )
        router = ContextAgentRouter(
            _provider(create),
            max_output_attempts=2,
        )

        with self.assertRaisesRegex(
            ContextAgentOutputError,
            "连续返回非法 strict tool 响应",
        ):
            await router.route(_agent_input())

        self.assertEqual(create.await_count, 2)

    async def test_rejects_non_contract_tool_arguments(self) -> None:
        create = mock.AsyncMock(
            return_value=_tool_response(
                {
                    "selected_chain_ids": ["chain-1"],
                    "create_new_chain": False,
                    "route_mode": "single_match",
                    "reason_summary": "已有链。",
                    "unexpected": "not allowed",
                }
            )
        )
        router = ContextAgentRouter(
            _provider(create),
            max_output_attempts=1,
        )

        with self.assertRaises(ContextAgentOutputError):
            await router.route(_agent_input())

    async def test_rejects_invalid_attempt_configuration(self) -> None:
        create = mock.AsyncMock()

        with self.assertRaisesRegex(
            ValueError,
            "max_output_attempts must be at least 1",
        ):
            ContextAgentRouter(
                _provider(create),
                max_output_attempts=0,
            )


if __name__ == "__main__":
    unittest.main()
