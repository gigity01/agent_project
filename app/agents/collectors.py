"""三个只读 Collector Agent 及其 Agent-as-Tool 包装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agents import Agent, ModelSettings
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


class CollectedFact(BaseModel):
    """可追溯到一次只读 Tool 查询的事实。"""

    statement: str = Field(min_length=1)
    source_tool: str = Field(min_length=1)
    resource_refs: list[str] = Field(default_factory=list)


class CollectorResult(BaseModel):
    """Collector 返回给 Planner 的统一结构化结果。"""

    collector_code: Literal[
        "document_collector",
        "context_collector",
        "operations_collector",
    ]
    summary: str = Field(min_length=1)
    facts: list[CollectedFact] = Field(default_factory=list)
    resource_refs: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class CollectorAgentSet:
    """三个 Collector 及提供给 Planner 的 Agent Tools。"""

    document: Agent[AgentToolContext]
    context: Agent[AgentToolContext]
    operations: Agent[AgentToolContext]
    planner_tools: tuple[FunctionTool, ...]


_COMMON_INSTRUCTIONS = """
你是只读信息收集 Agent。只能调用当前 Catalog 中提供的查询 Tool，不能执行写操作，
不能请求或执行 Handoff，不能规划业务 Task，也不能根据缺失信息编造事实。

请围绕输入中的 question 和资源范围调用最少且足够的查询 Tool。输出必须符合
CollectorResult：summary 只总结已验证事实；每个 fact 必须标明 source_tool 和
resource_refs；无法验证的内容放入 gaps。不得把 Tool 错误包装成已确认事实。
""".strip()


async def _extract_collector_result(run_result) -> str:
    """把嵌套 Collector 的结构化输出稳定序列化为 Tool JSON。"""
    result = CollectorResult.model_validate(run_result.final_output)
    return result.model_dump_json()


def _instructions(collector_code: str, responsibility: str) -> str:
    return (
        f"{_COMMON_INSTRUCTIONS}\n\n"
        f"你的 collector_code 必须是 {collector_code}。{responsibility}"
    )


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
            "document_collector",
            "只收集 Document、Artifact、ParentBlock、ChildChunk 和流水线状态。",
        ),
        tools=list(DOCUMENT_COLLECTOR_TOOLS),
        handoffs=[],
        model=model,
        model_settings=collector_settings,
        output_type=CollectorResult,
    )
    context_agent = Agent[AgentToolContext](
        name="Context Collector Agent",
        instructions=_instructions(
            "context_collector",
            "只收集 Turn、Chain、Node、Resource 和 RouteRecord 的持久化事实。",
        ),
        tools=list(CONTEXT_COLLECTOR_TOOLS),
        handoffs=[],
        model=model,
        model_settings=collector_settings,
        output_type=CollectorResult,
    )
    operations_agent = Agent[AgentToolContext](
        name="Operations Collector Agent",
        instructions=_instructions(
            "operations_collector",
            "只收集文档业务日志和 Agent Tool 审计事实。",
        ),
        tools=list(OPERATIONS_COLLECTOR_TOOLS),
        handoffs=[],
        model=model,
        model_settings=collector_settings,
        output_type=CollectorResult,
    )

    planner_tools = (
        document_agent.as_tool(
            tool_name="collect_document_information",
            tool_description="收集 Document 及其处理流水线的只读事实。",
            parameters=CollectorRequest,
            include_input_schema=True,
            max_turns=8,
            custom_output_extractor=_extract_collector_result,
        ),
        context_agent.as_tool(
            tool_name="collect_context_information",
            tool_description="收集 Conversation、Turn 和 Context Chain 的只读事实。",
            parameters=CollectorRequest,
            include_input_schema=True,
            max_turns=8,
            custom_output_extractor=_extract_collector_result,
        ),
        operations_agent.as_tool(
            tool_name="collect_operation_information",
            tool_description="收集业务日志与 Agent Tool 审计的只读事实。",
            parameters=CollectorRequest,
            include_input_schema=True,
            max_turns=8,
            custom_output_extractor=_extract_collector_result,
        ),
    )
    return CollectorAgentSet(
        document=document_agent,
        context=context_agent,
        operations=operations_agent,
        planner_tools=planner_tools,
    )
