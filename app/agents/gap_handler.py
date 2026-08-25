"""Evidence 与 Commit 之间的结构化信息缺口判断 Agent 模块。

职责说明：
- 作为 Planner 取证与任务提交之间的独立评估层，负责分析前置取证结果中遗留的未决信息与知识缺口。
- 输出结构化的 `GapDecision`，决定下一步流向：
  - `COMMIT`: 证据充分，进入 Plan Commit 规划阶段；
  - `COLLECT_MORE`: 缺口可通过已注册工具补查（第一版最多允许 1 次补查）；
  - `RETRY`: 取证遇到临时可重试故障；
  - `SYSTEM_FAILURE`: 取证遇到不可重试系统故障；
  - `CLARIFICATION`: 缺少必要用户输入或语义歧义，转交 Clarification 阶段；
  - `UNSUPPORTED`: 当前系统能力不支持满足该请求。
- 提供 `validate_gap_decision` 强制执行运行时确定性校验（如补查次数上限、重试证据支持等）。
"""

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
    """GapHandler 决定的下一步动作枚举类型。

    取值:
        COMMIT: 证据完备，直接进入 Plan 提交阶段。
        COLLECT_MORE: 允许且需要进行定向补充取证。
        RETRY: 工具发生可重试故障，请求重试。
        SYSTEM_FAILURE: 工具发生不可重试故障，报告系统错误。
        CLARIFICATION: 缺失用户意图或关键参数，请求用户澄清。
        UNSUPPORTED: 业务能力不支持该请求，标记 Plan 为 unsupported。
    """

    COMMIT = "COMMIT"
    COLLECT_MORE = "COLLECT_MORE"
    RETRY = "RETRY"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"
    CLARIFICATION = "CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"


class EvidenceRound(BaseModel):
    """单轮 Evidence 收集结果模型。

    属性:
        round_number: 轮次序号（1 为首次取证，2 为补充取证）。
        collector_results: 该轮各 Collector 返回的结果列表。
    """

    model_config = ConfigDict(extra="forbid")

    round_number: Literal[1, 2]
    collector_results: list[CollectorResult]


class GapHandlerInput(BaseModel):
    """GapHandler 决策输入上下文模型。

    属性:
        current_user_input: 用户原始请求文本。
        selected_context: 经 Context Selection 授权的历史链列表。
        evidence_rounds: 至今已执行的 Evidence 取证轮次列表（最多 2 轮）。
        collect_more_allowed: 当前是否允许再次发起补充取证。
    """

    model_config = ConfigDict(extra="forbid")

    current_user_input: str = Field(min_length=1)
    selected_context: list[ContextChain] = Field(default_factory=list)
    evidence_rounds: list[EvidenceRound] = Field(min_length=1, max_length=2)
    collect_more_allowed: bool


class GapDecision(BaseModel):
    """GapHandler 输出的结构化缺口决策模型。

    属性:
        action: 决策动作枚举。
        reason: 做出该决策的中文详细原因。
        follow_up: 当 action=COLLECT_MORE 时，指定的补充调查说明。
        clarification_kind: 当 action=CLARIFICATION 时，澄清分类（resource、intent 或 missing_parameter）。
        required_information: 当 action=CLARIFICATION 时，需要用户补充的具体信息点列表。
        known_resource_refs: 已知的相关资源标识引用列表。
    """

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
        """校验不同 action 对应的必填字段与互斥字段。"""
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
    """GapHandler 输出违反运行时可验证边界时抛出的异常。"""


# GapHandler 系统提示词指令
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
- SYSTEM_FAILURE：查询能力已注册且查询路径正确，但相关 Tool 本次 outcome=failed 且
  retryable=false，系统故障使当前无法安全继续。
- CLARIFICATION：缺失的是用户语义，selected_context 仍无法唯一确定，且业务 Tool
  不能替用户回答；必须给出分类和用户需要补充的信息。
- UNSUPPORTED：当前规划必需事实无法从 selected_context 获得，Business Docs 表明需要
  该事实，且 Registry 中没有任何可用查询能力。

不得把业务查询失败转成向用户询问系统状态。outcome=failed 且 retryable=false 时不得
自动 RETRY；Tool 已注册但不可重试的系统失败必须返回 SYSTEM_FAILURE，不得伪装成
COMMIT、RETRY 或 UNSUPPORTED。Business Docs 未写清但 Registry 存在对应查询能力时，
不得仅因文档缺失返回 UNSUPPORTED，应先使用该能力补查或依据实际 Tool 结果分类。
Schema Error 只表示模型输出不符合 GapDecision 契约，不能作为业务控制流。

collect_more_allowed=false 时绝不能返回 COLLECT_MORE。第一版最多只允许一次补查。
""".strip()


def build_gap_handler_agent(
    *,
    model: Any,
    model_settings: ModelSettings,
) -> Agent[AgentToolContext]:
    """构建 Planner GapHandler Agent 实例。

    配置要点：
    - 绑定 `search_business_docs`、`list_evidence_tools` 与 `find_evidence_tools` 三个元查询工具。
    - 结构化输出类型为 `GapDecision`。

    参数:
        model: 模型实例。
        model_settings: 模型基础配置。

    返回:
        Agent[AgentToolContext]: 配置好的 GapHandler Agent。
    """
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
    """将 LLM 最终输出解析并校验为 GapDecision Pydantic 对象。

    参数:
        final_output: LLM 最终输出对象或 JSON 字符串。

    返回:
        GapDecision: 校验通过的决策对象。
    """
    if isinstance(final_output, str):
        return GapDecision.model_validate_json(final_output)
    return GapDecision.model_validate(final_output)


def validate_gap_decision(
    decision: GapDecision,
    handler_input: GapHandlerInput,
) -> None:
    """对 Prompt 无法强制保证的状态机边界与失败分流语义做确定性断言校验。

    断言规则：
    1. 当 `collect_more_allowed=False` 时，禁止返回 `COLLECT_MORE`。
    2. 当决策为 `RETRY` 时，必须存在至少一个 `outcome=failed` 且 `retryable=True` 的 EvidenceItem 支持。
    3. 当决策为 `SYSTEM_FAILURE` 时，必须存在至少一个 `outcome=failed` 且 `retryable=False` 的 EvidenceItem 支持。

    参数:
        decision: 模型产出的决策对象。
        handler_input: 输入上下文。

    异常:
        GapDecisionError: 当校验不通过时抛出。
    """
    # 1. 补查次数上限校验
    if (
        decision.action == GapAction.COLLECT_MORE
        and not handler_input.collect_more_allowed
    ):
        raise GapDecisionError("第二轮 Evidence 后禁止再次 COLLECT_MORE")

    if decision.action not in {
        GapAction.RETRY,
        GapAction.SYSTEM_FAILURE,
    }:
        return

    # 2. 失败/重试证据支撑校验
    expected_retryable = decision.action == GapAction.RETRY
    has_matching_failure = any(
        item.outcome == "failed" and item.retryable == expected_retryable
        for evidence_round in handler_input.evidence_rounds
        for result in evidence_round.collector_results
        for item in result.evidence_items
    )
    if not has_matching_failure:
        expected_value = "true" if expected_retryable else "false"
        raise GapDecisionError(
            f"{decision.action.value} 必须由 outcome=failed 且 "
            f"retryable={expected_value} 的 Evidence 支持"
        )
