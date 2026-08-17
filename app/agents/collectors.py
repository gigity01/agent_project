"""三个只读 Collector Agent 及其 Agent-as-Tool 包装。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from agents import Agent, ModelSettings
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.tool import FunctionTool
from pydantic import BaseModel, Field

from app.agent_runtime.context import AgentToolContext
from app.modules.context.agent_tools.catalog import CONTEXT_COLLECTOR_TOOLS
from app.modules.document.agent_tools.catalog import DOCUMENT_COLLECTOR_TOOLS
from app.modules.operations.agent_tools.catalog import OPERATIONS_COLLECTOR_TOOLS


class CollectorRequest(BaseModel):
    """Planner 交给 Collector 的结构化信息收集范围。"""

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=100)
    turn_id: str | None = Field(default=None, max_length=100)
    document_ids: list[int] = Field(default_factory=list)
    chain_ids: list[str] = Field(default_factory=list)
    workflow_ids: list[str] = Field(default_factory=list)
    operation_ids: list[str] = Field(default_factory=list)


CollectorCode = Literal[
    "document_collector",
    "context_collector",
    "operations_collector",
]


class CollectorLLMResult(BaseModel):
    """Collector LLM 只负责解释证据并指出仍未确认的相关信息。"""

    summary: str = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """Collector 内一次只读 Function Tool Invocation 的真实记录。"""

    tool_name: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)

    # ToolCallItem：实际查询输入。
    arguments: dict[str, Any] = Field(default_factory=dict)

    # ToolCallOutputItem：实际查询结果。
    outcome: Literal["succeeded", "rejected", "failed"]
    result_code: str = Field(min_length=1)
    message: str
    retryable: bool
    resource_refs: list[str] = Field(default_factory=list)

    # 公共结果 envelope 之外的 Tool-specific business output。
    payload: dict[str, Any] = Field(default_factory=dict)


class CollectorResult(BaseModel):
    """Runtime 与 LLM 结果确定性组合后的 Collector 对外契约。

    ``resource_refs`` 是全部 EvidenceItem 资源引用的稳定去重并集，只表示
    本次调查涉及这些资源，不证明资源存在或状态正常。

    ``evidence_items`` 与 ``gaps`` 的组合语义固定为：两者都为空表示 no-op
    Collector；只有 gaps 表示没有取得 Evidence 且存在明确知识缺口；只有
    evidence_items 表示取得 Evidence 且未声明剩余缺口；两者都有表示取得部分
    Evidence 但仍有明确知识缺口。空 evidence_items 只表示 Collector 没有贡献
    Query Evidence，绝不表示业务事实已经验证。
    """

    collector_code: CollectorCode
    summary: str = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)
    resource_refs: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)


@dataclass(frozen=True)
class CollectorAgentSet:
    """三个 Collector 及提供给 Planner 的 Agent Tools。"""

    document: Agent[AgentToolContext]
    context: Agent[AgentToolContext]
    operations: Agent[AgentToolContext]
    planner_tools: tuple[FunctionTool, ...]


_COMMON_INSTRUCTIONS = """
你是只读信息收集 Agent。只能调用当前 Catalog 中提供的查询 Tool，
不能执行写操作，不能请求或执行 Handoff，不能规划业务 Task。

请围绕输入中的 question 和资源范围调用最少且足够的查询 Tool。

最终结构化输出只负责：
- summary：简洁总结查询 Tool 已验证的信息；
- gaps：列出调查后仍无法确认且与当前问题相关的信息；未调用 Tool 或 Tool failed
  本身不是 gap，应描述因此仍无法确认的业务事实。

不得编造 Tool 未返回的业务事实，不得把 rejected 或 failed Tool
结果描述成成功业务状态。

真实 Tool Call、Tool Output、资源引用和业务 Payload 由 Runtime
独立提取，不需要在 summary 中重复复制完整原始数据。
""".strip()


_COMMON_EVIDENCE_FIELDS = frozenset(
    {
        "outcome",
        "result_code",
        "message",
        "retryable",
        "resource_refs",
    }
)
_REQUIRED_EVIDENCE_FIELDS = _COMMON_EVIDENCE_FIELDS


def _extract_tool_arguments(item: ToolCallItem) -> dict[str, Any]:
    """从 SDK 原始 ToolCall item 提取实际 JSON object 查询参数。"""
    raw_item = item.raw_item

    if isinstance(raw_item, dict):
        raw_arguments = raw_item.get("arguments")
    else:
        raw_arguments = getattr(raw_item, "arguments", None)

    if not isinstance(raw_arguments, str):
        raise ValueError("Collector ToolCall 缺少 arguments")

    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("Collector ToolCall arguments 不是有效 JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Collector ToolCall arguments 必须是 JSON object")

    return parsed


def _normalize_tool_output(output: Any) -> dict[str, Any]:
    """把 SDK ToolCallOutputItem.output 规范化为 JSON object。"""
    if isinstance(output, BaseModel):
        return output.model_dump(mode="json")

    if isinstance(output, dict):
        return output

    if isinstance(output, str):
        parsed = json.loads(output)
        if not isinstance(parsed, dict):
            raise ValueError("Collector Tool output 必须是 JSON object")
        return parsed

    raise TypeError(f"Unsupported Collector Tool output: {type(output)!r}")


def _validate_tool_output_envelope(data: dict[str, Any]) -> None:
    """验证所有 Collector Query Tool 必须提供的公共结果字段。"""
    missing = _REQUIRED_EVIDENCE_FIELDS - data.keys()
    if missing:
        raise ValueError(
            f"Collector Tool output 缺少公共字段: {sorted(missing)}"
        )

    if data["outcome"] not in {"succeeded", "rejected", "failed"}:
        raise ValueError("非法 Tool outcome")


def _extract_evidence_items(new_items: list[Any]) -> list[EvidenceItem]:
    """按 call_id 配对真实 Tool Call 与 Output，并 fail closed。"""
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    for item in new_items:
        if not isinstance(item, ToolCallItem):
            continue

        call_id = item.call_id
        tool_name = item.tool_name
        if not call_id or not tool_name:
            raise ValueError("Collector ToolCall 缺少 call_id 或 tool_name")
        if call_id in calls:
            raise ValueError(f"重复 Tool call_id: {call_id}")
        calls[call_id] = (
            tool_name,
            _extract_tool_arguments(item),
        )

    evidence_items: list[EvidenceItem] = []
    consumed_call_ids: set[str] = set()
    for item in new_items:
        if not isinstance(item, ToolCallOutputItem):
            continue

        call_id = item.call_id
        if not call_id:
            raise ValueError("Collector ToolCallOutput 缺少 call_id")

        call = calls.get(call_id)
        if call is None:
            raise ValueError(
                f"找不到 ToolCallOutput 对应的 ToolCall: {call_id}"
            )
        if call_id in consumed_call_ids:
            raise ValueError(f"同一 ToolCall 出现多个 Output: {call_id}")

        tool_name, arguments = call
        data = _normalize_tool_output(item.output)
        _validate_tool_output_envelope(data)
        payload = {
            key: value
            for key, value in data.items()
            if key not in _COMMON_EVIDENCE_FIELDS
        }
        evidence_items.append(
            EvidenceItem(
                tool_name=tool_name,
                tool_call_id=call_id,
                arguments=arguments,
                outcome=data["outcome"],
                result_code=data["result_code"],
                message=data["message"],
                retryable=data["retryable"],
                resource_refs=data["resource_refs"],
                payload=payload,
            )
        )
        consumed_call_ids.add(call_id)

    missing_outputs = set(calls) - consumed_call_ids
    if missing_outputs:
        raise ValueError(
            f"Collector ToolCall 缺少 Output: {sorted(missing_outputs)}"
        )

    return evidence_items


def _build_collector_output_extractor(collector_code: CollectorCode):
    """为 Collector 创建固定来源代码的确定性输出提取器。"""

    async def extract(run_result) -> str:
        llm_result = CollectorLLMResult.model_validate(
            run_result.final_output
        )
        evidence_items = _extract_evidence_items(run_result.new_items)
        resource_refs = list(
            dict.fromkeys(
                resource_ref
                for item in evidence_items
                for resource_ref in item.resource_refs
            )
        )
        result = CollectorResult(
            collector_code=collector_code,
            summary=llm_result.summary,
            gaps=llm_result.gaps,
            resource_refs=resource_refs,
            evidence_items=evidence_items,
        )
        return result.model_dump_json()

    return extract


def _instructions(responsibility: str) -> str:
    return f"{_COMMON_INSTRUCTIONS}\n\n{responsibility}"


def build_collector_agents(
    *,
    model: Any,
    model_settings: ModelSettings,
) -> CollectorAgentSet:
    """创建三个无 Handoff Collector，并包装成 Planner 可调用的 Tool。"""
    collector_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=False)
    )
    document_agent = Agent[AgentToolContext](
        name="Document Collector Agent",
        instructions=_instructions(
            "只收集 Document、Artifact、ParentBlock、ChildChunk 和流水线状态。",
        ),
        tools=list(DOCUMENT_COLLECTOR_TOOLS),
        handoffs=[],
        model=model,
        model_settings=collector_settings,
        output_type=CollectorLLMResult,
    )
    context_agent = Agent[AgentToolContext](
        name="Context Collector Agent",
        instructions=_instructions(
            "只收集 Turn、Chain、Node、Resource 和 SelectionRecord 的持久化事实。",
        ),
        tools=list(CONTEXT_COLLECTOR_TOOLS),
        handoffs=[],
        model=model,
        model_settings=collector_settings,
        output_type=CollectorLLMResult,
    )
    operations_agent = Agent[AgentToolContext](
        name="Operations Collector Agent",
        instructions=_instructions(
            "只收集文档业务日志和 Agent Tool 审计事实。",
        ),
        tools=list(OPERATIONS_COLLECTOR_TOOLS),
        handoffs=[],
        model=model,
        model_settings=collector_settings,
        output_type=CollectorLLMResult,
    )
    planner_tools = (
        document_agent.as_tool(
            tool_name="collect_document_information",
            tool_description="收集 Document 及其处理流水线的只读事实。",
            parameters=CollectorRequest,
            include_input_schema=True,
            max_turns=8,
            custom_output_extractor=_build_collector_output_extractor(
                "document_collector"
            ),
        ),
        context_agent.as_tool(
            tool_name="collect_context_information",
            tool_description="收集 Conversation、Turn 和 Context Chain 的只读事实。",
            parameters=CollectorRequest,
            include_input_schema=True,
            max_turns=8,
            custom_output_extractor=_build_collector_output_extractor(
                "context_collector"
            ),
        ),
        operations_agent.as_tool(
            tool_name="collect_operation_information",
            tool_description="收集业务日志与 Agent Tool 审计的只读事实。",
            parameters=CollectorRequest,
            include_input_schema=True,
            max_turns=8,
            custom_output_extractor=_build_collector_output_extractor(
                "operations_collector"
            ),
        ),
    )
    return CollectorAgentSet(
        document=document_agent,
        context=context_agent,
        operations=operations_agent,
        planner_tools=planner_tools,
    )
