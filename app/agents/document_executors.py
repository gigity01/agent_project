"""按 Document Capability 隔离的受限 Executor Agents。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    StopAtTools,
    ToolExecutionConfig,
)

from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.errors import ToolNotAvailableError
from app.modules.document.agent_tools.catalog import (
    get_document_executor_tools,
)


DOCUMENT_EXECUTOR_MAX_FUNCTION_TOOL_CONCURRENCY = 1


@dataclass(frozen=True)
class DocumentExecutorAgentSet:
    """三个受限 Executor Agent 及其统一串行运行配置。"""

    process: Agent[AgentToolContext]
    build_chunks: Agent[AgentToolContext]
    index_vectors: Agent[AgentToolContext]
    run_config: RunConfig

    def require(self, executor_code: str) -> Agent[AgentToolContext]:
        agents = {
            "document.process": self.process,
            "document.build_chunks": self.build_chunks,
            "document.index_vectors": self.index_vectors,
        }
        try:
            return agents[executor_code]
        except KeyError as exc:
            raise ToolNotAvailableError(
                f"未知 Document Executor: {executor_code}"
            ) from exc


_BASE_EXECUTOR_INSTRUCTIONS = """
你是一个受限的 Document Capability Executor。Planner 已经确定本次 Task 的 WHAT；
你只能在当前 Capability 和输入 Payload 的范围内决定 HOW。可以多次调用暴露给你的
只读查询 Tool 确认状态，但不得扩展 Task 范围、规划新 Task、请求 Handoff、修改输入
资源标识或执行当前 Capability 之外的业务操作。Task Runtime 与数据库状态是事实层。
""".strip()


def _instructions(capability_code: str, primary_tool_name: str) -> str:
    return f"""
{_BASE_EXECUTOR_INSTRUCTIONS}

你正在执行已经确定的 {capability_code} Task。最终必须使用
{primary_tool_name} Tool 和原始 Task Payload 中的 document_id 完成本次 Task。
一旦调用该 Command Tool，本次 Run 会立即结束，其结构化 Tool Output 将直接交给
Task Runtime；不得自行宣称 Task 成功、失败或生成替代结果。
""".strip()


def _clone_executor(
    base_agent: Agent[AgentToolContext],
    *,
    name: str,
    capability_code: str,
    primary_tool_name: str,
) -> Agent[AgentToolContext]:
    return base_agent.clone(
        name=name,
        instructions=_instructions(capability_code, primary_tool_name),
        tools=list(get_document_executor_tools(capability_code)),
        handoffs=[],
        tool_use_behavior=StopAtTools(
            stop_at_tool_names=[primary_tool_name]
        ),
    )


def build_document_executor_agents(
    *,
    model: Any,
    model_settings: ModelSettings,
) -> DocumentExecutorAgentSet:
    """使用共享 Model 创建三个 capability-scoped Executor Agents。"""
    executor_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=False)
    )
    base_agent = Agent[AgentToolContext](
        name="Document Executor Agent",
        instructions=_BASE_EXECUTOR_INSTRUCTIONS,
        tools=[],
        handoffs=[],
        model=model,
        model_settings=executor_settings,
        output_type=None,
    )
    run_config = RunConfig(
        tracing_disabled=True,
        workflow_name="Document Capability Executor Run",
        tool_execution=ToolExecutionConfig(
            max_function_tool_concurrency=(
                DOCUMENT_EXECUTOR_MAX_FUNCTION_TOOL_CONCURRENCY
            )
        ),
    )
    return DocumentExecutorAgentSet(
        process=_clone_executor(
            base_agent,
            name="Process Document Executor Agent",
            capability_code="document.process",
            primary_tool_name="process_document",
        ),
        build_chunks=_clone_executor(
            base_agent,
            name="Build Chunks Executor Agent",
            capability_code="document.build_chunks",
            primary_tool_name="build_document_chunks",
        ),
        index_vectors=_clone_executor(
            base_agent,
            name="Index Vectors Executor Agent",
            capability_code="document.index_vectors",
            primary_tool_name="index_document_vectors",
        ),
        run_config=run_config,
    )
