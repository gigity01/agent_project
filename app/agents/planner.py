"""Planner Agent 与一次 SDK Runner 适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    Runner,
    ToolExecutionConfig,
)
from pydantic import BaseModel, Field

from app.agent_runtime.context import AgentToolContext
from app.agents.collectors import CollectorAgentSet
from app.modules.planning.agent_tools.catalog import PLANNER_TOOLS


MAX_COLLECTOR_CONCURRENCY = 3
DEFAULT_PLANNER_MAX_TURNS = 12


class PlanAgentOutput(BaseModel):
    """Planner 的非权威运行摘要；业务结果仍以数据库为准。"""

    summary: str = Field(min_length=1, max_length=2000)


@dataclass(frozen=True)
class PlannerAgentRunner:
    """把已配置 Agent 适配为 Application 使用的异步 Runner Port。"""

    agent: Agent[AgentToolContext]
    run_config: RunConfig
    max_turns: int = DEFAULT_PLANNER_MAX_TURNS

    async def run(
        self,
        *,
        user_input: str,
        context: AgentToolContext,
    ) -> Any:
        return await Runner.run(
            self.agent,
            user_input,
            context=context,
            max_turns=self.max_turns,
            run_config=self.run_config,
        )


_PLANNER_INSTRUCTIONS = """
你是业务 Planner。当前完整用户输入已经完成 Context 路由；你的职责是只基于可验证
事实创建一个可执行 Plan，不执行 Task，也不把最终文本当作业务事实。

必须遵守以下顺序和约束：
1. 先调用适用的 Collector Agent Tools 收集事实。三个 Collector 可以在同一轮并行
   调用，但每个 Collector 只调用一次，不得超过三个并发调用。
2. 只使用 Planning Function Tools 创建 Task。每项 Task 的 sequence 从 1 开始、
   唯一且连续，总数必须为 1～10。不要重试已经返回 succeeded 的创建调用。
3. 支持当前请求时，确认所有 Task 创建成功后调用 finalize_plan。无法由当前三个
   Capability 完成时调用 mark_plan_unsupported，并提供简短明确的原因。
4. 不得在 finalize_plan 或 mark_plan_unsupported 成功前结束运行。Tool 返回 rejected
   或 failed 时不得伪装成成功；无法安全恢复时结束运行，由 Application 标记重试。
5. 不创建 DAG、依赖边、Outbox、澄清 Handoff 或 Task Runtime 行为。

最终 Plan 状态、Task 状态和 task_ids 全部以数据库为准。你的 PlanAgentOutput.summary
只概述本次调用了哪些 Collector 和 Planning Tools，不得声称未由 Tool 成功持久化的结果。
""".strip()


def build_planner_agent(
    *,
    model: Any,
    model_settings: ModelSettings,
    collectors: CollectorAgentSet,
) -> PlannerAgentRunner:
    """装配 3 个 Collector Tools 与 5 个 Planning Tools。"""
    planner_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=True)
    )
    agent = Agent[AgentToolContext](
        name="Planner Agent",
        instructions=_PLANNER_INSTRUCTIONS,
        tools=[*collectors.planner_tools, *PLANNER_TOOLS],
        handoffs=[],
        model=model,
        model_settings=planner_settings,
        output_type=PlanAgentOutput,
    )
    run_config = RunConfig(
        tracing_disabled=True,
        workflow_name="Planner Run",
        tool_execution=ToolExecutionConfig(
            max_function_tool_concurrency=MAX_COLLECTOR_CONCURRENCY
        ),
    )
    return PlannerAgentRunner(agent=agent, run_config=run_config)
