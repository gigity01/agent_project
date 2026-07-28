"""只负责上下文关联判断的 Context Agent。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.agents.deepseek_provider import DeepSeekModelProvider
from app.schemas.context import (
    ContextAgentInput,
    ContextRouteDecision,
)


CONTEXT_ROUTE_TOOL_NAME = "submit_context_route"

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


class ContextAgentOutputError(RuntimeError):
    """DeepSeek 未按约定提交唯一且合法的 Context 路由结果。"""


def _resolve_local_schema_refs(
    value: Any,
    definitions: dict[str, Any],
) -> Any:
    """展开 Pydantic 生成的本地 ``$defs`` 引用。"""
    if isinstance(value, list):
        return [
            _resolve_local_schema_refs(item, definitions)
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition_name = reference.removeprefix("#/$defs/")
        definition = definitions.get(definition_name)
        if definition is None:
            raise ContextAgentOutputError(
                f"Context 路由 Schema 引用了未知定义: {definition_name}"
            )
        merged = deepcopy(definition)
        merged.update(
            {
                key: item
                for key, item in value.items()
                if key != "$ref"
            }
        )
        return _resolve_local_schema_refs(merged, definitions)

    return {
        key: _resolve_local_schema_refs(item, definitions)
        for key, item in value.items()
        if key != "$defs"
    }


def _normalize_strict_tool_schema(value: Any) -> Any:
    """移除展示元数据，并收紧对象 Schema。"""
    if isinstance(value, list):
        return [_normalize_strict_tool_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {
        key: _normalize_strict_tool_schema(item)
        for key, item in value.items()
        if key not in {"title", "default"}
    }
    if normalized.get("type") == "object":
        properties = normalized.get("properties", {})
        if isinstance(properties, dict):
            normalized["required"] = list(properties)
        normalized["additionalProperties"] = False
    return normalized


def build_context_route_tool_schema() -> dict[str, Any]:
    """从 Pydantic 契约生成 DeepSeek strict tool 参数 Schema。"""
    raw_schema = ContextRouteDecision.model_json_schema()
    definitions = raw_schema.get("$defs", {})
    resolved = _resolve_local_schema_refs(raw_schema, definitions)
    normalized = _normalize_strict_tool_schema(resolved)
    if not isinstance(normalized, dict):
        raise ContextAgentOutputError("Context 路由 Schema 不是 JSON 对象")
    return normalized


class ContextAgentRouter:
    """通过 DeepSeek strict tool call 返回结构化路由决定。"""

    def __init__(self, provider: DeepSeekModelProvider) -> None:
        self._client = provider.strict_tool_client
        self._model_name = provider.model_name
        self._tool_schema = build_context_route_tool_schema()

    async def route(
        self,
        agent_input: ContextAgentInput,
    ) -> ContextRouteDecision:
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=[
                {
                    "role": "system",
                    "content": CONTEXT_AGENT_INSTRUCTIONS,
                },
                {
                    "role": "user",
                    "content": agent_input.model_dump_json(indent=2),
                },
            ],
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

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if len(tool_calls) != 1:
            raise ContextAgentOutputError(
                "Context Agent 必须且只能返回一个 Tool Call"
            )

        tool_call = tool_calls[0]
        if tool_call.function.name != CONTEXT_ROUTE_TOOL_NAME:
            raise ContextAgentOutputError(
                "Context Agent 返回了非预期 Tool: "
                f"{tool_call.function.name}"
            )

        try:
            return ContextRouteDecision.model_validate_json(
                tool_call.function.arguments
            )
        except ValidationError as exc:
            raise ContextAgentOutputError(
                "Context Agent Tool 参数不符合路由契约"
            ) from exc
