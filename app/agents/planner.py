"""Planner 取证、提交两个执行阶段及其 SDK Runner 适配器。"""

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
PLANNER_EVIDENCE_MAX_FUNCTION_TOOL_CONCURRENCY = 3
PLANNER_COMMIT_MAX_FUNCTION_TOOL_CONCURRENCY = 1


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
    """以同一上下文串联 Planner 取证与提交阶段。"""

    evidence_agent: Agent[AgentToolContext]
    commit_agent: Agent[AgentToolContext]
    evidence_run_config: RunConfig
    commit_run_config: RunConfig
    max_turns: int = DEFAULT_PLANNER_MAX_TURNS

    async def run(
        self,
        *,
        user_input: str,
        context: AgentToolContext,
    ) -> Any:
        evidence_result = await Runner.run(
            self.evidence_agent,
            user_input,
            context=context,
            max_turns=self.max_turns,
            run_config=self.evidence_run_config,
        )
        return await Runner.run(
            self.commit_agent,
            evidence_result.to_input_list(),
            context=context,
            max_turns=self.max_turns,
            run_config=self.commit_run_config,
        )


_PLANNER_BASE_INSTRUCTIONS = """
你是业务 Planner。当前完整用户输入已经完成 Context 路由；你的职责是只基于可验证
事实创建一个可执行 Plan，不执行 Task，也不把最终文本当作业务事实。Planner 决定
WHAT，Task Runtime 和受限 Executor 决定 HOW。
""".strip()


_PLANNER_EVIDENCE_INSTRUCTIONS = f"""
{_PLANNER_BASE_INSTRUCTIONS}

当前是 Evidence Phase。根据请求判断需要哪些可验证事实，自主选择 Document、Context
或 Operations Collector Tool；不得调用与当前规划无关的 Collector，也不得重复相同
取证。多个彼此独立的 Collector 可以在同一轮发出，每轮最多 3 个 Tool Call。

你在本阶段不能创建、发布或终止 Plan，也不能向用户澄清。收集完所需事实后，只生成
简短的取证就绪说明并结束本阶段；Collector Tool Call 与结构化 Tool Output 会由运行时
完整传递给 Commit Phase，不得编造或改写其中的事实。
""".strip()


_PLANNER_COMMIT_INSTRUCTIONS = f"""
{_PLANNER_BASE_INSTRUCTIONS}

当前是 Commit Phase。之前的输入历史已经包含 Evidence Phase 的 Collector Tool Call、
结构化 Tool Output 和取证就绪说明；本阶段不能再次调用 Collector，只能基于这些证据
提交 Plan、澄清或 unsupported 结果。

Collector Tool Output 中：
1. evidence_items 是 Runtime 从实际 Query Tool 调用中确定性提取的证据，
   是规划业务状态时的主要依据。
2. summary 和 gaps 是 Collector 对证据的解释，仅用于辅助理解；
   不得使用 summary 覆盖或修改 evidence_items。
3. outcome=succeeded 只表示 Query Tool 成功执行，
   不表示 payload 中业务资源的状态为 succeeded。
4. 业务状态必须读取 succeeded EvidenceItem 的 payload。
5. rejected / failed EvidenceItem 的 payload 不得作为成功业务事实；
   应结合 outcome、result_code、message、retryable 判断本次取证是否足够。
6. resource_refs 只表示本次调查涉及的资源，
   不证明资源存在或状态正常。
7. summary 与 evidence_items 冲突时，以 evidence_items 为准。

必须遵守以下约束：
1. 只使用 Planning Function Tools 创建 Task。每项 Task 的 sequence 从 1 开始、
   唯一且连续，总数必须为 1～10。不要重试已经返回 succeeded 的创建调用。
2. 支持当前请求时，确认所有 Task 创建成功后调用 finalize_plan。无法由当前三个
   Capability 完成时调用 mark_plan_unsupported，并提供简短明确的原因。
3. 不得在 finalize_plan 或 mark_plan_unsupported 成功前结束运行。Tool 返回 rejected
   或 failed 时不得伪装成成功；无法安全恢复时结束运行，由 Application 标记重试。
4. 资源不唯一、意图有多种合理解释或缺少必要参数时，使用 clarification_handoff；
   不得把可由 Collector 验证的信息转成澄清问题。
5. 只通过 task_ref 和 depends_on_task_refs 表达 DAG；不得直接创建依赖边、Outbox 或
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
    """从同一基础 Planner 克隆物理隔离的取证与提交阶段。"""
    evidence_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=True)
    )
    commit_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=False)
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
        model_settings=commit_settings,
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

    base_planner = Agent[AgentToolContext](
        name="Planner Agent",
        instructions=_PLANNER_BASE_INSTRUCTIONS,
        tools=[],
        handoffs=[],
        model=model,
        model_settings=model_settings,
        output_type=None,
    )
    evidence_agent = base_planner.clone(
        instructions=_PLANNER_EVIDENCE_INSTRUCTIONS,
        tools=list(collectors.planner_tools),
        handoffs=[],
        model_settings=evidence_settings,
    )
    commit_agent = base_planner.clone(
        instructions=_PLANNER_COMMIT_INSTRUCTIONS,
        tools=list(PLANNER_TOOLS),
        handoffs=[clarification_handoff],
        model_settings=commit_settings,
        tool_use_behavior=StopAtTools(
            stop_at_tool_names=[
                "finalize_plan",
                "mark_plan_unsupported",
            ]
        ),
    )
    evidence_run_config = RunConfig(
        tracing_disabled=True,
        workflow_name="Planner Evidence Run",
        tool_execution=ToolExecutionConfig(
            max_function_tool_concurrency=(
                PLANNER_EVIDENCE_MAX_FUNCTION_TOOL_CONCURRENCY
            )
        ),
    )
    commit_run_config = RunConfig(
        tracing_disabled=True,
        workflow_name="Planner Commit Run",
        tool_execution=ToolExecutionConfig(
            max_function_tool_concurrency=(
                PLANNER_COMMIT_MAX_FUNCTION_TOOL_CONCURRENCY
            )
        ),
    )
    return PlannerAgentRunner(
        evidence_agent=evidence_agent,
        commit_agent=commit_agent,
        evidence_run_config=evidence_run_config,
        commit_run_config=commit_run_config,
    )
