"""按 Document Capability 隔离的受限 Executor Agent 模块。

职责说明：
- 针对 Document 模块的三项独立执行能力（`document.process`、`document.build_chunks`、`document.index_vectors`）提供受限 Executor Agent。
- 各 Executor Agent 仅绑定其对应 Capability 授权的只读查询工具与唯一状态变更命令工具。
- 配置 `StopAtTools` 拦截机制，一旦调用核心命令工具，Agent Run 立即中止并将结构化工具输出移交给确定性 Runtime 适配器，防止 LLM 文本篡改执行事实。
- 强制串行执行 (`parallel_tool_calls=False`, `max_function_tool_concurrency=1`)。
"""

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

# 执行器工具最大并发度，固定为 1 严格串行执行
DOCUMENT_EXECUTOR_MAX_FUNCTION_TOOL_CONCURRENCY = 1


@dataclass(frozen=True)
class DocumentExecutorAgentSet:
    """三种 Capability 受限执行器 Agent 及其统一运行配置容器。

    属性:
        process: 文档处理/清洗执行器 Agent。
        build_chunks: 父子切块构建执行器 Agent。
        index_vectors: 向量生成与 Qdrant 索引执行器 Agent。
        run_config: 串行运行配置。
    """

    process: Agent[AgentToolContext]
    build_chunks: Agent[AgentToolContext]
    index_vectors: Agent[AgentToolContext]
    run_config: RunConfig

    def require(self, executor_code: str) -> Agent[AgentToolContext]:
        """根据 capability 代码获取对应的受限 Executor Agent 实例。

        参数:
            executor_code: 执行器能力代码（如 `document.process`、`document.build_chunks`、`document.index_vectors`）。

        返回:
            Agent[AgentToolContext]: 对应的受限 Agent 实例。

        异常:
            ToolNotAvailableError: 当 executor_code 未知时抛出。
        """
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


# 基础执行器通用系统指令
_BASE_EXECUTOR_INSTRUCTIONS = """
你是一个受限的 Document Capability Executor。Planner 已经确定本次 Task 的 WHAT；
你只能在当前 Capability 和输入 Payload 的范围内决定 HOW。可以多次调用暴露给你的
只读查询 Tool 确认状态，但不得扩展 Task 范围、规划新 Task、请求 Handoff、修改输入
资源标识或执行当前 Capability 之外的业务操作。Task Runtime 与数据库状态是事实层。
""".strip()


def _instructions(capability_code: str, primary_tool_name: str) -> str:
    """组合特定 Capability 执行器的专用系统提示词指令。

    参数:
        capability_code: 能力标识代码。
        primary_tool_name: 该能力绑定的核心命令工具名称。

    返回:
        str: 拼接后的执行器完整指令文本。
    """
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
    """从基础 Agent 克隆出仅绑定特定命令与查询工具的专用 Executor Agent 实例。

    配置要点：
    - 绑定 capability 专用的工具集合（只读查询 + 核心写入命令）。
    - 配置 `StopAtTools(stop_at_tool_names=[primary_tool_name])` 确保命令执行后立即停止。

    参数:
        base_agent: 基础 Agent 模板。
        name: 新 Agent 名称。
        capability_code: 能力代码。
        primary_tool_name: 核心命令工具名称。

    返回:
        Agent[AgentToolContext]: 克隆后的受限 Agent 实例。
    """
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
    """构建用于 Task Runtime 驱动的三个 Capability-Scoped Executor Agent 实例。

    参数:
        model: 模型实例。
        model_settings: 基础模型设置。

    返回:
        DocumentExecutorAgentSet: 包含三个能力执行器与串行 RunConfig 的集合对象。
    """
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
