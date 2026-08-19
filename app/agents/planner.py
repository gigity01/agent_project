"""Planner Evidence、Gap 判断、Commit 及其 SDK Runner 适配器。"""

from __future__ import annotations

import asyncio
import json
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

from app.agent_runtime.business_docs import load_service_map
from app.agent_runtime.context import AgentToolContext
from app.agents.collectors import (
    CollectorAgentSet,
    CollectorResult,
    extract_collector_results,
)
from app.agents.gap_handler import (
    EvidenceRound,
    GapAction,
    GapDecision,
    GapDecisionError,
    GapHandlerInput,
    build_gap_handler_agent,
    parse_gap_decision,
    validate_gap_decision,
)
from app.modules.planning.agent_tools.catalog import PLANNER_TOOLS
from app.modules.planning.application.dto import (
    MarkPlanNeedsClarificationInput,
    MarkPlanUnsupportedInput,
    PlannerContextInput,
)
from app.modules.planning.application.errors import PlanningRetryRequested


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
    """以同一上下文串联 Evidence、Gap 判断与 Commit。"""

    evidence_agent: Agent[AgentToolContext]
    gap_handler_agent: Agent[AgentToolContext]
    commit_agent: Agent[AgentToolContext]
    clarification_agent: Agent[AgentToolContext]
    evidence_run_config: RunConfig
    gap_handler_run_config: RunConfig
    commit_run_config: RunConfig
    clarification_run_config: RunConfig
    max_turns: int = DEFAULT_PLANNER_MAX_TURNS

    async def run(
        self,
        *,
        planner_input: PlannerContextInput,
        context: AgentToolContext,
    ) -> Any:
        first_evidence_result = await Runner.run(
            self.evidence_agent,
            planner_input.model_dump_json(indent=2),
            context=context,
            max_turns=self.max_turns,
            run_config=self.evidence_run_config,
        )
        first_collector_results = extract_collector_results(
            first_evidence_result.new_items
        )
        evidence_rounds = [
            EvidenceRound(
                round_number=1,
                collector_results=first_collector_results,
            )
        ]
        if _evidence_is_ready_for_commit(first_collector_results):
            return await self._run_commit(
                evidence_history=first_evidence_result.to_input_list(),
                context=context,
            )

        first_gap_result, decision = await self._run_gap_handler(
            planner_input=planner_input,
            evidence_rounds=evidence_rounds,
            collect_more_allowed=True,
            context=context,
        )
        if decision.action != GapAction.COLLECT_MORE:
            return await self._resolve_gap_decision(
                decision=decision,
                gap_result=first_gap_result,
                evidence_history=first_evidence_result.to_input_list(),
                context=context,
            )

        second_evidence_result = await Runner.run(
            self.evidence_agent,
            _append_internal_message(
                first_evidence_result.to_input_list(),
                "Evidence Follow-up",
                {
                    "instruction": decision.follow_up,
                    "constraint": (
                        "只补充该未知事实；不得重复已经成功完成且与该未知无关的查询。"
                    ),
                },
            ),
            context=context,
            max_turns=self.max_turns,
            run_config=self.evidence_run_config,
        )
        evidence_rounds.append(
            EvidenceRound(
                round_number=2,
                collector_results=extract_collector_results(
                    second_evidence_result.new_items
                ),
            )
        )
        second_gap_result, second_decision = await self._run_gap_handler(
            planner_input=planner_input,
            evidence_rounds=evidence_rounds,
            collect_more_allowed=False,
            context=context,
        )
        return await self._resolve_gap_decision(
            decision=second_decision,
            gap_result=second_gap_result,
            evidence_history=second_evidence_result.to_input_list(),
            context=context,
        )

    async def _run_gap_handler(
        self,
        *,
        planner_input: PlannerContextInput,
        evidence_rounds: list[EvidenceRound],
        collect_more_allowed: bool,
        context: AgentToolContext,
    ) -> tuple[Any, GapDecision]:
        handler_input = GapHandlerInput(
            current_user_input=planner_input.current_user_input,
            selected_context=planner_input.context_chains,
            evidence_rounds=evidence_rounds,
            collect_more_allowed=collect_more_allowed,
        )
        result = await Runner.run(
            self.gap_handler_agent,
            handler_input.model_dump_json(indent=2),
            context=context,
            max_turns=self.max_turns,
            run_config=self.gap_handler_run_config,
        )
        decision = parse_gap_decision(result.final_output)
        validate_gap_decision(decision, handler_input)
        return result, decision

    async def _resolve_gap_decision(
        self,
        *,
        decision: GapDecision,
        gap_result: Any,
        evidence_history: list[Any],
        context: AgentToolContext,
    ) -> Any:
        if decision.action == GapAction.COMMIT:
            return await self._run_commit(
                evidence_history=_append_internal_message(
                    evidence_history,
                    "Gap Decision",
                    decision.model_dump(mode="json"),
                ),
                context=context,
            )
        if decision.action == GapAction.RETRY:
            raise PlanningRetryRequested(decision.reason)
        if decision.action == GapAction.SYSTEM_FAILURE:
            raise RuntimeError(
                f"Planning 前置取证发生系统故障: {decision.reason}"
            )
        if decision.action == GapAction.UNSUPPORTED:
            await _mark_gap_unsupported(context, decision.reason)
            return gap_result
        if decision.action == GapAction.CLARIFICATION:
            clarification = ClarificationHandoffInput(
                clarification_kind=decision.clarification_kind,
                reason=decision.reason,
                required_information=decision.required_information,
                known_resource_refs=decision.known_resource_refs,
            )
            await _mark_gap_clarification(context, clarification)
            return await Runner.run(
                self.clarification_agent,
                clarification.model_dump_json(indent=2),
                context=context,
                max_turns=self.max_turns,
                run_config=self.clarification_run_config,
            )
        raise GapDecisionError("COLLECT_MORE 未在 Evidence 补查边界内处理")

    async def _run_commit(
        self,
        *,
        evidence_history: list[Any],
        context: AgentToolContext,
    ) -> Any:
        return await Runner.run(
            self.commit_agent,
            evidence_history,
            context=context,
            max_turns=self.max_turns,
            run_config=self.commit_run_config,
        )


def _evidence_is_ready_for_commit(results: list[CollectorResult]) -> bool:
    evidence_items = [
        item for result in results for item in result.evidence_items
    ]
    return (
        bool(evidence_items)
        and all(item.outcome == "succeeded" for item in evidence_items)
        and not any(
            gap.strip() for result in results for gap in result.gaps
        )
    )


def _append_internal_message(
    history: list[Any],
    label: str,
    payload: Any,
) -> list[Any]:
    return [
        *history,
        {
            "role": "user",
            "content": (
                f"{label}:\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def _planning_scope(
    context: AgentToolContext,
) -> tuple[Any, str, str]:
    if (
        context.planning_services is None
        or context.plan_id is None
        or context.conversation_id is None
    ):
        raise RuntimeError("Gap 决策缺少 Planning 上下文")
    return context.planning_services, context.plan_id, context.conversation_id


async def _mark_gap_unsupported(
    context: AgentToolContext,
    reason: str,
) -> None:
    services, plan_id, _ = _planning_scope(context)
    await asyncio.to_thread(
        services.mark_plan_unsupported.execute,
        MarkPlanUnsupportedInput(plan_id=plan_id, reason=reason),
    )


async def _mark_gap_clarification(
    context: AgentToolContext,
    data: ClarificationHandoffInput,
) -> None:
    services, plan_id, conversation_id = _planning_scope(context)
    await asyncio.to_thread(
        services.mark_plan_needs_clarification.execute,
        MarkPlanNeedsClarificationInput(
            plan_id=plan_id,
            conversation_id=conversation_id,
            kind=data.clarification_kind,
            reason=data.reason,
            required_information=data.required_information,
            known_resource_refs=data.known_resource_refs,
        ),
    )


_SERVICE_MAP = load_service_map()


_PLANNER_BASE_INSTRUCTIONS = f"""
你是业务 Planner。输入中的 current_user_input 是当前请求，context_chains 只包含
Context Selection 授权读取的完整历史 Chain；当前 Turn 不属于这些历史 Chain。
你的职责是只基于可验证
事实创建一个可执行 Plan，不执行 Task，也不把最终文本当作业务事实。Planner 决定
WHAT，Task Runtime 和受限 Executor 决定 HOW。

以下 Service Map 只帮助理解请求所属业务，不授予 Tool 权限，也不扩大 Context Read Set：

{_SERVICE_MAP}
""".strip()


_PLANNER_EVIDENCE_INSTRUCTIONS = f"""
{_PLANNER_BASE_INSTRUCTIONS}

当前是 Evidence Phase。根据请求判断需要哪些可验证事实，自主选择 Document、Context
或 Operations Collector Tool；不得调用与当前规划无关的 Collector，也不得重复相同
取证。多个彼此独立的 Collector 可以在同一轮发出，每轮最多 3 个 Tool Call。

Collector 已经返回足够证据的事实，不得重复调查。对于当前规划所需但仍无法确认的事实，
必须明确写入对应 Collector 的 gap；不得因为 Tool 未调用而默认事实成立。
gap 只描述未知事实，不决定 clarification、retry、unsupported 或后续规划动作。

你在本阶段不能创建、发布或终止 Plan，也不能向用户澄清。收集完所需事实后，只生成
简短的取证就绪说明并结束本阶段；Collector Tool Call 与结构化 Tool Output 会由运行时
完整传递给 Commit Phase，不得编造或改写其中的事实。
""".strip()


_PLANNER_COMMIT_INSTRUCTIONS = f"""
{_PLANNER_BASE_INSTRUCTIONS}

当前是 Commit Phase。之前的输入历史已经包含 Evidence Phase 的 Collector Tool Call、
结构化 Tool Output 和取证就绪说明。前置 Gap 层已经确认现有 Evidence 足够进入规划；
本阶段不得重新分类 gap，也不能再次调用 Collector，只能基于现有证据创建 Task、发布
Plan，或处理执行 Capability 本身不支持、用户意图/参数仍不唯一的情况。

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
8. EvidenceItem.arguments 表示 Query Tool 实际使用的查询条件；payload 表示该查询
   实际返回的业务数据。判断 Evidence 是否支持某项业务结论时必须同时考虑
   arguments 与 payload。
9. evidence_items 为空只表示该 Collector 未提供可验证业务证据，不表示任何业务状态
   已经验证，不得仅根据 summary 创建依赖业务状态的 Task。
   Tool succeeded 但业务对象不存在仍是有效查询事实，必须按 payload 的空结果理解。

必须遵守以下约束：
1. 只使用 Planning Function Tools 创建 Task。每项 Task 的 sequence 从 1 开始、
   唯一且连续，总数必须为 1～10。不要重试已经返回 succeeded 的创建调用。
2. 支持当前请求时，确认所有 Task 创建成功后调用 finalize_plan。无法由当前三个
   Capability 完成时调用 mark_plan_unsupported，并提供简短明确的原因。
3. 不得在 finalize_plan 或 mark_plan_unsupported 成功前结束运行。Tool 返回 rejected
   或 failed 时不得伪装成成功；无法安全恢复时结束运行，由 Application 标记重试。
4. 只有创建 Task 时仍发现用户意图有多种合理解释或缺少必要业务参数，才使用
   clarification_handoff；不得把系统状态或可由 Collector 验证的信息转成澄清问题。
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
    """装配物理隔离的 Evidence、GapHandler 与 Commit 阶段。"""
    evidence_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=True)
    )
    commit_settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=False)
    )
    gap_handler_agent = build_gap_handler_agent(
        model=model,
        model_settings=model_settings,
    )
    clarification_agent = Agent[AgentToolContext](
        name="Clarification Agent",
        handoff_description="把已确认的信息缺口转成一个简洁、可回答的问题。",
        instructions=(
            "根据输入或 Handoff 历史中的结构化缺口，只生成一个直接问题。"
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
        await _mark_gap_clarification(ctx.context, data)

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
    gap_handler_run_config = RunConfig(
        tracing_disabled=True,
        workflow_name="Planner Gap Handler Run",
        tool_execution=ToolExecutionConfig(
            max_function_tool_concurrency=1
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
    clarification_run_config = RunConfig(
        tracing_disabled=True,
        workflow_name="Planner Clarification Run",
        tool_execution=ToolExecutionConfig(
            max_function_tool_concurrency=1
        ),
    )
    return PlannerAgentRunner(
        evidence_agent=evidence_agent,
        gap_handler_agent=gap_handler_agent,
        commit_agent=commit_agent,
        clarification_agent=clarification_agent,
        evidence_run_config=evidence_run_config,
        gap_handler_run_config=gap_handler_run_config,
        commit_run_config=commit_run_config,
        clarification_run_config=clarification_run_config,
    )
