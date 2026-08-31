"""三个只读 Collector Agent 及其 Agent-as-Tool 包装模块。

职责说明：
- 提供 Document、Context、Operations 三个独立的只读取证 Collector Agent 定义。
- 强制内部关闭并行 Tool Call (`parallel_tool_calls=False`)，各 Collector 只能访问对应领域的只读查询工具。
- 将 Collector Agent 包装为 Planner Evidence 阶段可调用的 Agent-as-Tool (`collect_document_information` 等)。
- 实现确定性的证据提取与校验机制 (`_extract_evidence_items`, `extract_collector_results`)，按 `call_id` 配对工具调用与输出，严格执行 fail-closed 语义。
"""

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
    """Planner 提交给 Collector Agent 的结构化信息收集请求模型。

    属性:
        question: 本次取证的自然语言目标或具体问题。
        conversation_id: 可选的会话 ID 范围约束。
        turn_id: 可选的对话轮次 ID 约束。
        document_ids: 待调查的文档 ID 列表。
        chain_ids: 待调查的上下文链 ID 列表。
        workflow_ids: 待调查的工作流 ID 列表。
        operation_ids: 待调查的操作令牌 ID 列表。
    """

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=100)
    turn_id: str | None = Field(default=None, max_length=100)
    document_ids: list[int] = Field(default_factory=list)
    chain_ids: list[str] = Field(default_factory=list)
    workflow_ids: list[str] = Field(default_factory=list)
    operation_ids: list[str] = Field(default_factory=list)


# 支持的 Collector 代码标识
CollectorCode = Literal[
    "document_collector",
    "context_collector",
    "operations_collector",
]

# Planner 暴露的 Tool 名称到 Collector 代码的映射字典
COLLECTOR_TOOL_CODES: dict[str, CollectorCode] = {
    "collect_document_information": "document_collector",
    "collect_context_information": "context_collector",
    "collect_operation_information": "operations_collector",
}


class CollectorLLMResult(BaseModel):
    """Collector Agent 中 LLM 生成的结构化解释与缺口声明模型。

    注意：LLM 只负责解释证据与指出未决缺口，底层真实证据由 Runtime 提取。

    属性:
        summary: 基于实际调用工具返回的事实提炼的中文总结。
        gaps: 调查后仍无法确认且与当前问题直接相关的明确业务事实缺口列表。
    """

    summary: str = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """Collector 内部单次只读 Function Tool 调用的底层真实执行记录。

    属性:
        tool_name: 实际调用的工具名称。
        tool_call_id: 工具调用的唯一标识 ID。
        original_tool_call_id: 首次查询的 Tool Call ID，用于关联局部重试尝试。
        attempt_count: 当前逻辑查询的调用次数，首次调用为 1。
        arguments: 实际传入的查询参数字典。
        outcome: 执行终态分类（succeeded、rejected 或 failed）。
        result_code: 机器可读的业务结果码。
        message: 结果或错误描述信息。
        retryable: 是否为可重试错误。
        resource_refs: 本次查询涉及的资源引用列表。
        payload: 公共结果封套之外的工具特定业务数据载荷。
    """

    tool_name: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)
    original_tool_call_id: str = Field(min_length=1)
    attempt_count: int = Field(ge=1)

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
    """Runtime 真实执行证据与 LLM 解释确定性组合后的 Collector 对外输出契约。

    语义规范：
    - `resource_refs`: 全部 EvidenceItem 资源引用的稳定去重并集，仅表示调查涉及这些资源，不证明其存在。
    - `evidence_items`: 实际取得的底层执行证据列表。
    - `gaps`: 未确认的业务缺口列表。
    - 空 `evidence_items` 仅表示未贡献可验证证据，绝不代表业务事实已验证。

    属性:
        collector_code: Collector 类型代码。
        summary: LLM 总结文本。
        gaps: 遗留缺口列表。
        resource_refs: 涉及的资源引用列表。
        evidence_items: 底层证据项列表。
    """

    collector_code: CollectorCode
    summary: str = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)
    resource_refs: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)


@dataclass(frozen=True)
class CollectorAgentSet:
    """三个只读 Collector Agent 实例及其向 Planner 暴露的 Agent-as-Tool 工具元组。

    属性:
        document: Document 只读收集 Agent。
        context: Context 只读收集 Agent。
        operations: Operations 只读日志收集 Agent。
        planner_tools: 包装后的三个 FunctionTool 实例。
    """

    document: Agent[AgentToolContext]
    context: Agent[AgentToolContext]
    operations: Agent[AgentToolContext]
    planner_tools: tuple[FunctionTool, ...]


# Collector Agent 通用系统提示词指令
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


# 公共工具结果封套字段集合
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
    """从 SDK 原始 ToolCallItem 中安全提取 JSON 对象形式的查询参数。

    参数:
        item: SDK 原始 ToolCallItem。

    返回:
        dict[str, Any]: 解析后的查询参数字典。

    异常:
        ValueError: 当参数缺失、非合法 JSON 或非 dict 时抛出。
    """
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
    """将 SDK ToolCallOutputItem 中的 output 归一化解析为 JSON 字典。

    参数:
        output: 工具输出（Pydantic 模型、dict 或 JSON 字符串）。

    返回:
        dict[str, Any]: 字典对象。

    异常:
        TypeError: 当输出类型不支持时抛出。
        ValueError: 当解析结果非 JSON 对象时抛出。
    """
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
    """验证所有 Collector Query Tool 的输出字典是否完整包含公共封套字段。

    参数:
        data: 工具输出数据字典。

    异常:
        ValueError: 缺少必要公共字段或 outcome 取值非法时抛出。
    """
    missing = _REQUIRED_EVIDENCE_FIELDS - data.keys()
    if missing:
        raise ValueError(
            f"Collector Tool output 缺少公共字段: {sorted(missing)}"
        )

    if data["outcome"] not in {"succeeded", "rejected", "failed"}:
        raise ValueError("非法 Tool outcome")


def _extract_evidence_items(new_items: list[Any]) -> list[EvidenceItem]:
    """按 call_id 严格配对 ToolCall 与 ToolOutput，构建不可变的 EvidenceItem 列表。

    执行 fail-closed 安全校验：
    - 缺少 call_id、tool_name 或存在重复 call_id 立即报错。
    - 出现孤立 ToolCall（缺少 Output）或孤立 Output 立即报错。

    参数:
        new_items: Collector Run 产出的 SDK 条目列表。

    返回:
        list[EvidenceItem]: 结构化的底层证据项列表。

    异常:
        ValueError: 当任何配对或封套校验失败时抛出。
    """
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
                original_tool_call_id=call_id,
                attempt_count=1,
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


def extract_collector_results(new_items: list[Any]) -> list[CollectorResult]:
    """从顶层 Evidence Run 的输出条目中提取并配对各 Collector 的结构化结果。

    参数:
        new_items: Evidence Agent Run 产出的 SDK 条目列表。

    返回:
        list[CollectorResult]: 提取并验证通过的 Collector 结果列表。

    异常:
        ValueError: 当条目不合法、call_id 重复或来源代码不匹配时抛出。
    """
    calls: dict[str, CollectorCode] = {}
    for item in new_items:
        if not isinstance(item, ToolCallItem):
            continue

        call_id = item.call_id
        tool_name = item.tool_name
        if not call_id or not tool_name:
            raise ValueError("Evidence Collector ToolCall 缺少 call_id 或 tool_name")
        if call_id in calls:
            raise ValueError(f"重复 Evidence Tool call_id: {call_id}")

        collector_code = COLLECTOR_TOOL_CODES.get(tool_name)
        if collector_code is None:
            raise ValueError(f"Evidence Run 包含非 Collector Tool: {tool_name}")
        calls[call_id] = collector_code

    results: list[CollectorResult] = []
    consumed_call_ids: set[str] = set()
    for item in new_items:
        if not isinstance(item, ToolCallOutputItem):
            continue

        call_id = item.call_id
        if not call_id:
            raise ValueError("Evidence Collector ToolCallOutput 缺少 call_id")
        expected_code = calls.get(call_id)
        if expected_code is None:
            raise ValueError(
                "找不到 Evidence Collector ToolCallOutput 对应的 ToolCall: "
                f"{call_id}"
            )
        if call_id in consumed_call_ids:
            raise ValueError(
                f"同一 Evidence Collector ToolCall 出现多个 Output: {call_id}"
            )

        result = CollectorResult.model_validate(
            _normalize_tool_output(item.output)
        )
        if result.collector_code != expected_code:
            raise ValueError(
                "CollectorResult 来源与调用 Tool 不一致: "
                f"expected={expected_code}, actual={result.collector_code}"
            )
        results.append(result)
        consumed_call_ids.add(call_id)

    missing_outputs = set(calls) - consumed_call_ids
    if missing_outputs:
        raise ValueError(
            "Evidence Collector ToolCall 缺少 Output: "
            f"{sorted(missing_outputs)}"
        )
    return results


def _build_collector_output_extractor(collector_code: CollectorCode):
    """为指定 Collector 创建固定来源代码的确定性输出提取器函数。

    参数:
        collector_code: 目标 Collector 代码标识。

    返回:
        Callable: 异步提取函数，将 RunResult 转换为 JSON 序列化的 CollectorResult。
    """

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
    """组合通用只读指令与特定 Collector 职责说明。

    参数:
        responsibility: 特定 Collector 职责说明文本。

    返回:
        str: 拼接后的完整系统指令。
    """
    return f"{_COMMON_INSTRUCTIONS}\n\n{responsibility}"


def build_collector_agents(
    *,
    model: Any,
    model_settings: ModelSettings,
) -> CollectorAgentSet:
    """初始化构建三个只读 Collector Agent，并将其包装为 Planner 可调用的 FunctionTool。

    配置要点：
    - 各 Collector 强制设置 `parallel_tool_calls=False`。
    - 绑定对应的 Catalog 只读工具列表。
    - `as_tool` 时配置 `custom_output_extractor` 实现确定性结果提取。

    参数:
        model: 模型实例。
        model_settings: 基础模型设置。

    返回:
        CollectorAgentSet: 包含三个 Agent 及三个 Planner Tool 的容器对象。
    """
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
