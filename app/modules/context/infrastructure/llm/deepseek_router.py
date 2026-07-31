"""基于 DeepSeek strict Tool 的 Context Router。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.infrastructure.llm.deepseek.provider import DeepSeekModelProvider
from app.modules.context.application.dto import ContextAgentInput
from app.modules.context.domain.enums import ContextRouteMode
from app.modules.context.domain.models import ContextRouteDecision
from app.modules.context.infrastructure.llm.strict_schema_adapter import (
    ContextAgentOutputError,
    build_context_route_tool_schema,
)


CONTEXT_ROUTE_TOOL_NAME = "submit_context_route"
DEFAULT_CONTEXT_AGENT_OUTPUT_ATTEMPTS = 2

CONTEXT_AGENT_INSTRUCTIONS = """
你是上下文管理和消息路由 Agent。

你的唯一职责是判断当前完整用户输入与哪些已有上下文链相关，
以及是否包含与所有已有链都无关的新上下文。

规则：

1. 用户输入可以同时关联一条或多条已有链。
2. 不得拆分、改写或摘要当前用户输入。
3. 明确关联多条链时，返回全部相关 chain_id。
4. 与所有已有链无关时，创建新链。
5. 同时包含已有上下文和新上下文时，返回已有 chain_id，
   并标记需要创建新链。
6. 存在关联但无法判断具体归属时，选择 last_active_at 最新的链。
7. 不得生成计划、任务、操作、权限或执行建议。
8. 不得修改链内容、资源或时间戳。
9. 必须且只能调用 submit_context_route 提交结构化路由结果，
   不得输出普通文本。
10. resource_queue 按从旧到新排列，越靠近队尾表示最近越活跃；
    队列只用于判断上下文关联，不得据此生成业务操作。

route_mode 与字段必须满足：

- single_match：恰好选择一条已有链，不创建新链。
- multi_match：选择至少两条已有链，不创建新链。
- new_chain：不选择已有链，创建新链。
- existing_and_new：选择至少一条已有链，同时创建新链。
- fallback_latest：恰好选择 last_active_at 最新的一条已有链，不创建新链。

reason_summary 只能简要说明上下文关联依据，不得包含后续业务计划或执行建议。
""".strip()


def _new_chain_decision_without_model() -> ContextRouteDecision:
    """没有候选链时直接返回确定性结果，避免无意义模型调用。"""
    return ContextRouteDecision(
        selected_chain_ids=[],
        create_new_chain=True,
        route_mode=ContextRouteMode.NEW_CHAIN,
        reason_summary="当前会话没有可关联的已有上下文链。",
    )


class DeepSeekContextRouter:
    """通过 DeepSeek strict tool call 返回结构化路由决定。"""

    def __init__(
        self,
        provider: DeepSeekModelProvider,
        *,
        max_output_attempts: int = DEFAULT_CONTEXT_AGENT_OUTPUT_ATTEMPTS,
    ) -> None:
        if max_output_attempts < 1:
            raise ValueError("max_output_attempts must be at least 1")
        self._client = provider.strict_tool_client
        self._model_name = provider.model_name
        self._tool_schema = build_context_route_tool_schema()
        self._max_output_attempts = max_output_attempts

    async def route(
        self,
        agent_input: ContextAgentInput,
    ) -> ContextRouteDecision:
        """返回结构化路由结果；没有候选链时不调用模型。"""
        if not agent_input.chains:
            return _new_chain_decision_without_model()

        last_error: ContextAgentOutputError | None = None
        for attempt in range(self._max_output_attempts):
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=self._build_messages(
                    agent_input,
                    retry=attempt > 0,
                ),
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": CONTEXT_ROUTE_TOOL_NAME,
                            "description": "提交唯一的 Context 路由决定。",
                            "strict": True,
                            "parameters": self._tool_schema,
                        },
                    }
                ],
                tool_choice={
                    "type": "function",
                    "function": {
                        "name": CONTEXT_ROUTE_TOOL_NAME,
                    },
                },
                parallel_tool_calls=False,
                temperature=0,
                max_tokens=512,
                extra_body={
                    "thinking": {
                        "type": "disabled",
                    }
                },
            )

            try:
                return self._parse_response(response)
            except ContextAgentOutputError as exc:
                last_error = exc

        raise ContextAgentOutputError(
            "Context Agent 连续返回非法 strict tool 响应"
        ) from last_error

    @staticmethod
    def _build_messages(
        agent_input: ContextAgentInput,
        *,
        retry: bool,
    ) -> list[dict[str, str]]:
        user_content = agent_input.model_dump_json(indent=2)
        if retry:
            user_content = (
                "上一次响应未形成唯一且合法的 submit_context_route "
                "调用。请重新判断，并且只能调用该工具。\n\n"
                f"{user_content}"
            )
        return [
            {
                "role": "system",
                "content": CONTEXT_AGENT_INSTRUCTIONS,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

    @staticmethod
    def _parse_response(response: Any) -> ContextRouteDecision:
        choices = getattr(response, "choices", None)
        if not choices:
            raise ContextAgentOutputError("Context Agent 没有返回 choice")

        message = getattr(choices[0], "message", None)
        if message is None:
            raise ContextAgentOutputError("Context Agent choice 缺少 message")

        tool_calls = getattr(message, "tool_calls", None) or []
        if len(tool_calls) != 1:
            raise ContextAgentOutputError(
                "Context Agent 必须且只能返回一个 Tool Call"
            )

        tool_call = tool_calls[0]
        function = getattr(tool_call, "function", None)
        if function is None:
            raise ContextAgentOutputError(
                "Context Agent Tool Call 缺少 function"
            )
        if function.name != CONTEXT_ROUTE_TOOL_NAME:
            raise ContextAgentOutputError(
                "Context Agent 返回了非预期 Tool: "
                f"{function.name}"
            )

        arguments = getattr(function, "arguments", None)
        if not isinstance(arguments, str) or not arguments.strip():
            raise ContextAgentOutputError(
                "Context Agent Tool Call 缺少 arguments"
            )

        try:
            return ContextRouteDecision.model_validate_json(arguments)
        except ValidationError as exc:
            raise ContextAgentOutputError(
                "Context Agent Tool 参数不符合路由契约"
            ) from exc
