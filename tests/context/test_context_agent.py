"""Context Agent strict tool Schema、确定性分支与响应解析测试。"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import mock

from app.modules.context.infrastructure.llm.deepseek_router import (
    CONTEXT_AGENT_INSTRUCTIONS,
    CONTEXT_SELECTION_TOOL_NAME,
    DeepSeekContextRouter,
)
from app.modules.context.infrastructure.llm.strict_schema_adapter import (
    ContextAgentOutputError,
    build_context_selection_tool_schema,
)
from app.modules.context.application.dto import ContextAgentInput
from app.modules.context.domain.models import (
    ContextChain,
    ContextResourceQueue,
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
                                name=CONTEXT_SELECTION_TOOL_NAME,
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


class _EventLogger:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, **fields) -> bool:
        self.events.append({"event": event, **fields})
        return True


class _FailingEventLogger:
    def write(self, event: str, **fields) -> bool:
        raise OSError("metrics unavailable")


class ContextSelectionToolSchemaTest(unittest.TestCase):
    def test_schema_is_generated_from_pydantic_without_local_refs(self) -> None:
        schema = build_context_selection_tool_schema()

        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {"relevant_chain_ids", "reason_summary"},
        )
        serialized = json.dumps(schema)
        self.assertNotIn("$defs", schema)
        self.assertNotIn("$ref", serialized)
        self.assertNotIn("minLength", serialized)
        self.assertNotIn("maxLength", serialized)


class ContextAgentRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_service_map_does_not_expand_context_authority(self) -> None:
        self.assertIn("Document Processing", CONTEXT_AGENT_INSTRUCTIONS)
        self.assertIn("Context Management", CONTEXT_AGENT_INSTRUCTIONS)
        self.assertIn("Operations", CONTEXT_AGENT_INSTRUCTIONS)
        self.assertIn("不授予 Tool 权限", CONTEXT_AGENT_INSTRUCTIONS)
        self.assertIn("不扩大", CONTEXT_AGENT_INSTRUCTIONS)

    async def test_without_existing_chains_returns_empty_selection_without_llm(self) -> None:
        create = mock.AsyncMock()
        router = ContextAgentRouter(_provider(create))

        decision = await router.route(_agent_input(with_chain=False))

        self.assertEqual(decision.relevant_chain_ids, [])
        self.assertEqual(
            decision.reason_summary,
            "当前 Conversation 没有历史上下文。",
        )
        create.assert_not_awaited()

    async def test_forces_one_strict_tool_and_parses_arguments(self) -> None:
        create = mock.AsyncMock(
            return_value=_tool_response(
                {
                    "relevant_chain_ids": ["chain-1"],
                    "reason_summary": "当前输入延续已有文档方案。",
                }
            )
        )
        router = ContextAgentRouter(_provider(create))

        decision = await router.route(_agent_input())

        self.assertEqual(decision.relevant_chain_ids, ["chain-1"])
        request = create.await_args.kwargs
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(
            request["tool_choice"]["function"]["name"],
            CONTEXT_SELECTION_TOOL_NAME,
        )
        self.assertFalse(request["parallel_tool_calls"])
        self.assertEqual(request["temperature"], 0)
        function = request["tools"][0]["function"]
        self.assertTrue(function["strict"])
        self.assertEqual(function["parameters"]["type"], "object")
        self.assertFalse(function["parameters"]["additionalProperties"])

    async def test_observability_failure_does_not_change_selection(self) -> None:
        create = mock.AsyncMock(
            return_value=_tool_response(
                {
                    "relevant_chain_ids": ["chain-1"],
                    "reason_summary": "延续已有上下文。",
                }
            )
        )
        router = ContextAgentRouter(
            _provider(create),
            event_logger=_FailingEventLogger(),
        )

        decision = await router.route(_agent_input())

        self.assertEqual(decision.relevant_chain_ids, ["chain-1"])

    async def test_retries_once_after_invalid_tool_response(self) -> None:
        create = mock.AsyncMock(
            side_effect=[
                _invalid_response(),
                _tool_response(
                    {
                        "relevant_chain_ids": ["chain-1"],
                        "reason_summary": "第二次返回合法路由。",
                    }
                ),
            ]
        )
        event_logger = _EventLogger()
        router = ContextAgentRouter(
            _provider(create),
            max_output_attempts=2,
            event_logger=event_logger,
        )

        decision = await router.route(_agent_input())

        self.assertEqual(decision.relevant_chain_ids, ["chain-1"])
        self.assertEqual(create.await_count, 2)
        second_request = create.await_args_list[1].kwargs
        self.assertIn(
            "上一次响应未形成唯一且合法",
            second_request["messages"][1]["content"],
        )
        self.assertEqual(
            [event["event"] for event in event_logger.events],
            [
                "context_selection_invalid_output",
                "context_selection_llm_completed",
            ],
        )
        self.assertEqual(
            event_logger.events[0][
                "context_selection_invalid_output_count"
            ],
            1,
        )
        self.assertEqual(
            event_logger.events[1]["context_selection_retry_count"],
            1,
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
                    "relevant_chain_ids": ["chain-1"],
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
