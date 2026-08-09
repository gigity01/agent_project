"""Planner Agent、独立 Collector Tools 与一次 SDK Runner 适配器。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from agents import (
    Agent,
    ModelSettings,
    RunContextWrapper,
    RunConfig,
    Runner,
    StopAtTools,
    ToolExecutionConfig,
    handoff,
)
from pydantic import BaseModel, Field

from app.agent_runtime.context import AgentToolContext
from app.agents.collectors import CollectorAgentSet
from app.modules.planning.agent_tools.catalog import PLANNER_TOOLS
from app.modules.planning.application.dto import (
    MarkPlanNeedsClarificationInput,
)


DEFAULT_PLANNER_MAX_TURNS = 12
PLANNER_MAX_FUNCTION_TOOL_CONCURRENCY = 3


class ClarificationHandoffInput(BaseModel):
    clarification_kind: Literal[
        "resource",
        "intent",
        "missing_parameter",
    ]
    reason: str = Field(min_length=1, max_length=4000)
    required_information: list[str] = Field(min_length=1, max_length=10)
    known_resource_refs: list[str] = Field(default_factory=list, max_length=50)


class ClarificationAgentOutput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


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
1. 先根据请求判断需要哪些可验证事实，自主选择 Document、Context 或 Operations
   Collector Tool；不得调用与当前规划无关的 Collector。多个彼此独立的
   Collector 可以在同一轮发出，每轮最多发出 3 个 Tool Call。
2. 只有在所需 Collector 返回后才能创建 Task。不得在同一轮中混合调用
   Collector Tool 与 Planning Function Tool，也不得重复相同的取证调用。
3. 只使用 Planning Function Tools 创建 Task。每项 Task 的 sequence 从 1 开始、
   唯一且连续，总数必须为 1～10。不要重试已经返回 succeeded 的创建调用。
4. 支持当前请求时，确认所有 Task 创建成功后调用 finalize_plan。无法由当前三个
   Capability 完成时调用 mark_plan_unsupported，并提供简短明确的原因。
5. 不得在 finalize_plan 或 mark_plan_unsupported 成功前结束运行。Tool 返回 rejected
   或 failed 时不得伪装成成功；无法安全恢复时结束运行，由 Application 标记重试。
6. 资源不唯一、意图有多种合理解释或缺少必要参数时，使用 clarification_handoff；
   不得把可由 Collector 验证的信息转成澄清问题。
7. 只通过 task_ref 和 depends_on_task_refs 表达 DAG；不得直接创建依赖边、Outbox 或
   Task Runtime 行为。DAG 最大深度为 3，同一 Plan Task 总数不超过 10。

最终 Plan 状态、Task 状态和 task_ids 全部以数据库为准。不要生成业务总结；
finalize_plan 或 mark_plan_unsupported 成功后当前 Run 会立即结束。
""".strip()


def build_planner_agent(
    *,
    model: Any,
    model_settings: ModelSettings,
    collectors: CollectorAgentSet,
) -> PlannerAgentRunner:
    """装配三个独立 Collector Tools 与 Planning Tools。"""
    planner_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=True)
    )
    clarification_agent = Agent[AgentToolContext](
        name="Clarification Agent",
        handoff_description="把已确认的信息缺口转成一个简洁、可回答的问题。",
        instructions=(
            "根据 Handoff 历史中的结构化缺口，只生成一个直接问题。"
            "不得规划 Task、调用 Tool 或假设用户答案。"
        ),
        tools=[],
        handoffs=[],
        model=model,
        model_settings=planner_settings,
        output_type=ClarificationAgentOutput,
    )

    async def on_clarification_handoff(
        ctx: RunContextWrapper[AgentToolContext],
        data: ClarificationHandoffInput,
    ) -> None:
        context = ctx.context
        if (
            context.planning_services is None
            or context.plan_id is None
            or context.conversation_id is None
        ):
            raise RuntimeError("Clarification Handoff 缺少 Planning 上下文")
        await asyncio.to_thread(
            context.planning_services.mark_plan_needs_clarification.execute,
            MarkPlanNeedsClarificationInput(
                plan_id=context.plan_id,
                conversation_id=context.conversation_id,
                kind=data.clarification_kind,
                reason=data.reason,
                required_information=data.required_information,
                known_resource_refs=data.known_resource_refs,
            ),
        )

    clarification_handoff = handoff(
        clarification_agent,
        tool_name_override="clarification_handoff",
        tool_description_override="转交 Clarification Agent 生成用户澄清问题。",
        on_handoff=on_clarification_handoff,
        input_type=ClarificationHandoffInput,
    )

    agent = Agent[AgentToolContext](
        name="Planner Agent",
        instructions=_PLANNER_INSTRUCTIONS,
        tools=[*collectors.planner_tools, *PLANNER_TOOLS],
        handoffs=[clarification_handoff],
        model=model,
        model_settings=planner_settings,
        output_type=None,
        tool_use_behavior=StopAtTools(
            stop_at_tool_names=[
                "finalize_plan",
                "mark_plan_unsupported",
            ]
        ),
    )
    run_config = RunConfig(
        tracing_disabled=True,
        workflow_name="Planner Run",
        tool_execution=ToolExecutionConfig(
            max_function_tool_concurrency=PLANNER_MAX_FUNCTION_TOOL_CONCURRENCY
        ),
    )
    return PlannerAgentRunner(agent=agent, run_config=run_config)
