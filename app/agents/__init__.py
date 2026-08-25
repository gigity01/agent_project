"""面向 Planner 和 Runtime 的业务 Agent 定义包。

本包定义了基于 OpenAI Agents SDK 与 LangGraph 编排的各核心 Agent：
- `collectors.py`: Document、Context、Operations 三个只读取证 Collector 及其 Agent-as-Tool 适配。
- `gap_handler.py`: Evidence 收集与 Plan Commit 之间的结构化信息缺口判断 Agent (`GapDecision`)。
- `planner.py`: Planner Agent Runner，使用 StateGraph 状态机串联两阶段取证、缺口决策、Plan Commit 与 Clarification。
- `document_executors.py`: 面向三种文档能力（process、build_chunks、index_vectors）的受限执行器 Agent (`DocumentExecutorAgentSet`)。
"""

from app.agents.collectors import (
    CollectorAgentSet,
    CollectorRequest,
    CollectorResult,
    EvidenceItem,
    build_collector_agents,
    extract_collector_results,
)
from app.agents.document_executors import (
    DocumentExecutorAgentSet,
    build_document_executor_agents,
)
from app.agents.gap_handler import (
    EvidenceRound,
    GapAction,
    GapDecision,
    GapHandlerInput,
    build_gap_handler_agent,
)
from app.agents.planner import (
    ClarificationAgentOutput,
    ClarificationHandoffInput,
    PlannerAgentRunner,
    build_planner_agent,
)

__all__ = [
    "CollectorAgentSet",
    "CollectorRequest",
    "CollectorResult",
    "EvidenceItem",
    "EvidenceRound",
    "GapAction",
    "GapDecision",
    "GapHandlerInput",
    "DocumentExecutorAgentSet",
    "ClarificationAgentOutput",
    "ClarificationHandoffInput",
    "build_collector_agents",
    "build_gap_handler_agent",
    "build_document_executor_agents",
    "extract_collector_results",
    "PlannerAgentRunner",
    "build_planner_agent",
]
