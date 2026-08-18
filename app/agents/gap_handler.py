"""Evidence 与 Commit 之间的结构化信息缺口判断层。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from agents import Agent, ModelSettings
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent_runtime.business_docs import search_business_docs
from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.tool_registry import (
    find_evidence_tools,
    list_evidence_tools,
)
from app.agents.collectors import CollectorResult
from app.modules.context.domain.models import ContextChain


class GapAction(str, Enum):
    COMMIT = "COMMIT"
    COLLECT_MORE = "COLLECT_MORE"
    RETRY = "RETRY"
    CLARIFICATION = "CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"


class EvidenceRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_number: Literal[1, 2]
    collector_results: list[CollectorResult]


class GapHandlerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_user_input: str = Field(min_length=1)
    selected_context: list[ContextChain] = Field(default_factory=list)
    evidence_rounds: list[EvidenceRound] = Field(min_length=1, max_length=2)
    collect_more_allowed: bool


class GapDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: GapAction
    reason: str = Field(min_length=1, max_length=4000)
    follow_up: str | None = Field(default=None, min_length=1, max_length=4000)
    clarification_kind: Literal[
        "resource",
        "intent",
        "missing_parameter",
    ] | None = None
    required_information: list[str] = Field(default_factory=list, max_length=10)
    known_resource_refs: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "GapDecision":
        if self.action == GapAction.COLLECT_MORE:
            if self.follow_up is None:
                raise ValueError("COLLECT_MORE 必须提供 follow_up")
        elif self.follow_up is not None:
            raise ValueError("只有 COLLECT_MORE 可以提供 follow_up")

        if self.action == GapAction.CLARIFICATION:
            if self.clarification_kind is None:
                raise ValueError(
                    "CLARIFICATION 必须提供 clarification_kind"
                )
            if not self.required_information:
                raise ValueError(
                    "CLARIFICATION 必须提供 required_information"
                )
        elif (
            self.clarification_kind is not None
            or self.required_information
            or self.known_resource_refs
        ):
            raise ValueError(
                "只有 CLARIFICATION 可以提供澄清分类、所需信息和已知资源"
            )
        return self


class GapDecisionError(ValueError):
    """GapHandler 输出违反运行时可验证边界。"""


GAP_HANDLER_INSTRUCTIONS = """
你是 Planner GapHandler，位于 Evidence 和 Commit 之间。你不创建 Task、不发布 Plan、
不执行业务动作，也不改写 Collector Evidence。你的唯一职责是判断当前未知信息为何仍未
解决，以及下一步应如何消除它。

输入中的 selected_context 只包含 Context Selection 已授权的历史 Read Set。
evidence_rounds 按发生顺序保存 CollectorResult；较晚 Evidence 可以解决较早 round 中的
gap。EvidenceItem 是实际查询事实，gap 只是 Collector 在该轮结束后仍未知的事实。
若 Evidence Agent 没有产生任何 EvidenceItem，或只产生 rejected/failed EvidenceItem，
即使 Collector 漏写 gap，也必须判断当前请求是否真的不需要业务事实；不得直接放行依赖
业务状态的 Task。

判断时遵守：
1. 先判断每个 gap 是否是当前请求形成安全 Plan 的必要前置事实。无关 gap 返回 COMMIT。
2. 对必要 gap，使用 search_business_docs 确认业务规则和推荐查询路径，再用
   list_evidence_tools 或 find_evidence_tools 确认代码当前真实注册的能力。
3. Business Docs 描述系统应该如何工作；Tool Registry 描述代码当前实际注册了什么。
   两者冲突时 Tool Registry 优先，不得假装存在未注册 Tool。
4. Registry 只证明能力存在，不授予当前调用权限。Context 查询仍只能针对
   selected_context 中的 Chain/Turn；不得扩大 Read Set。
5. Tool succeeded 但业务对象不存在是一项有效 Evidence，不得自动改写成“没查到”的
   gap。rejected/failed 也不得作为成功业务事实。

只返回一个结构化 GapDecision：
- COMMIT：gap 不阻塞当前请求，或后续 Evidence 已经解决它。
- COLLECT_MORE：系统有已注册查询能力，但上一轮没有查询或查询策略不完整；follow_up
  必须只描述需要补充确认的事实，不得重复无关成功查询。
- RETRY：查询路径正确，并且相关 Tool 本次 outcome=failed 且 retryable=true。
- CLARIFICATION：缺失的是用户语义，selected_context 仍无法唯一确定，且业务 Tool
  不能替用户回答；必须给出分类和用户需要补充的信息。
- UNSUPPORTED：当前规划必需事实无法从 selected_context 获得，Business Docs 表明需要
  该事实，且 Registry 中没有任何可用查询能力。

不得把业务查询失败转成向用户询问系统状态。outcome=failed 且 retryable=false 时不得
自动 RETRY；先判断是否确实没有能力而应 UNSUPPORTED。若 Tool 已注册但非重试系统失败
使你无法安全判断，不得伪装成 COMMIT、RETRY 或 UNSUPPORTED，应让本次结构化判断失败，
由 Planning Application 按系统失败处理。

collect_more_allowed=false 时绝不能返回 COLLECT_MORE。第一版最多只允许一次补查。
""".strip()


def build_gap_handler_agent(
    *,
    model: Any,
    model_settings: ModelSettings,
) -> Agent[AgentToolContext]:
    settings = model_settings.resolve(
        ModelSettings(parallel_tool_calls=False)
    )
    return Agent[AgentToolContext](
        name="Planner Gap Handler",
        instructions=GAP_HANDLER_INSTRUCTIONS,
        tools=[
            search_business_docs,
            list_evidence_tools,
            find_evidence_tools,
        ],
        handoffs=[],
        model=model,
        model_settings=settings,
        output_type=GapDecision,
    )


def parse_gap_decision(final_output: Any) -> GapDecision:
    if isinstance(final_output, str):
        return GapDecision.model_validate_json(final_output)
    return GapDecision.model_validate(final_output)


def validate_gap_decision(
    decision: GapDecision,
    handler_input: GapHandlerInput,
) -> None:
    """对 Prompt 无法强制的循环和 retry 语义做确定性校验。"""
    if (
        decision.action == GapAction.COLLECT_MORE
        and not handler_input.collect_more_allowed
    ):
        raise GapDecisionError("第二轮 Evidence 后禁止再次 COLLECT_MORE")

    if decision.action != GapAction.RETRY:
        return

    has_retryable_failure = any(
        item.outcome == "failed" and item.retryable
        for evidence_round in handler_input.evidence_rounds
        for result in evidence_round.collector_results
        for item in result.evidence_items
    )
    if not has_retryable_failure:
        raise GapDecisionError(
            "RETRY 必须由 outcome=failed 且 retryable=true 的 Evidence 支持"
        )
