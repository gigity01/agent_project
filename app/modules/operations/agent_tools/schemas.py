"""Operations Function Tool 请求与响应 Schema 定义。

定义 Operations Collector Agent 所使用的只读 Tool 输入/输出 Pydantic 模型，
包含业务日志检索、操作/工作流时间线、失败分析、Tool 审计及调用序列查询。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.operations.application.dto import (
    AgentToolAuditEvent,
    AgentToolAuditQuery,
    DocumentBusinessLogEvent,
    DocumentBusinessLogQuery,
    DocumentExecutionTimelineResult,
    DocumentFailureTimelineResult,
    DocumentTimelineQuery,
    DocumentOperationTimelineQuery,
    DocumentOperationTimelineResult,
    DocumentWorkflowTimelineQuery,
    DocumentWorkflowTimelineResult,
    DateRangeQuery,
    ToolInvocationTimelineItem,
)


class QueryDocumentBusinessLogsToolInput(DocumentBusinessLogQuery):
    """文档业务日志查询工具输入参数。

    继承自 DocumentBusinessLogQuery，支持按文档 ID、知识库 ID、流水线阶段、事件类型、日志级别和时间范围筛选。
    """


class QueryDocumentLogEventsToolInput(DocumentBusinessLogQuery):
    """统一关联模型下的文档业务事件查询工具输入参数。

    支持按 workflow_id、operation_id、attempt、文档、阶段等多维关联键精确筛选。
    """


class GetDocumentOperationTimelineToolInput(DocumentOperationTimelineQuery):
    """单次文档操作（operation_id）时间线查询工具输入参数。"""


class GetDocumentWorkflowTimelineToolInput(DocumentWorkflowTimelineQuery):
    """完整文档工作流（workflow_id）跨阶段与重试时间线查询工具输入参数。"""


class GetDocumentExecutionTimelineToolInput(DocumentTimelineQuery):
    """单篇文档（document_id）全生命周期执行时间线查询工具输入参数。"""


class GetDocumentFailureTimelineToolInput(DocumentTimelineQuery):
    """单篇文档（document_id）失败事件与错误摘要时间线查询工具输入参数。"""


class QueryAgentToolAuditsToolInput(AgentToolAuditQuery):
    """Agent Tool 调用审计查询工具输入参数。

    支持按 trace_id、agent_run_id、conversation_id、turn_id、task_id、Agent 名称、Tool 名称等条件过滤。
    """


class ToolTimelineToolInput(DateRangeQuery):
    """Tool 调用时间线通用查询输入基础模型。

    Attributes:
        agent_names: 过滤的 Agent 名称列表。
        tool_names: 过滤的 Tool 名称列表。
        created_from: 开始时间。
        created_to: 截止时间。
        limit: 最大返回条数（1-500，默认 500）。
    """

    agent_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    created_from: datetime | None = None
    created_to: datetime | None = None
    limit: int = Field(default=500, ge=1, le=500)


class GetTaskToolTimelineToolInput(ToolTimelineToolInput):
    """Task 级别的 Tool 调用时间线查询工具输入参数。

    Attributes:
        task_id: 关联的 Task 唯一标识符。
    """

    task_id: str = Field(min_length=1, max_length=200)


class GetAgentRunToolTimelineToolInput(ToolTimelineToolInput):
    """Agent Run 级别的 Tool 调用时间线查询工具输入参数。

    Attributes:
        agent_run_id: 关联的 Agent Run 唯一标识符。
    """

    agent_run_id: str = Field(min_length=1, max_length=200)


class OperationsToolResult(BaseModel):
    """Operations 模块 Agent Tool 统一标准响应信封。

    Attributes:
        outcome: 结果状态，枚举值："succeeded"（成功）、"rejected"（拒绝/权限不足等）、"failed"（内部错误）。
        result_code: 结构化结果码（如 "document_log_events_queried"）。
        message: 面向 Agent 或用户的描述信息。
        retryable: 是否可安全重试。
        resource_refs: 本次查询涉及的资源引用标识列表（如 ["document:1", "workflow:wf-1"]）。
    """

    outcome: Literal["succeeded", "rejected", "failed"]
    result_code: str
    message: str
    retryable: bool
    resource_refs: list[str]


class QueryDocumentBusinessLogsToolOutput(OperationsToolResult):
    """文档业务日志查询响应输出。

    Attributes:
        events: 匹配的文档业务日志事件列表。
        next_cursor: 分页游标，若无更多数据则为 None。
    """

    events: list[DocumentBusinessLogEvent] = Field(default_factory=list)
    next_cursor: str | None = None


class QueryDocumentLogEventsToolOutput(QueryDocumentBusinessLogsToolOutput):
    """统一关联模型下的文档业务事件查询响应输出。"""


class GetDocumentOperationTimelineToolOutput(OperationsToolResult):
    """单次文档操作时间线查询响应输出。

    Attributes:
        timeline: 单次操作的聚合事件时间线；若未查到相关日志则为 None。
    """

    timeline: DocumentOperationTimelineResult | None = None


class GetDocumentWorkflowTimelineToolOutput(OperationsToolResult):
    """完整文档工作流时间线查询响应输出。

    Attributes:
        timeline: 工作流聚合事件时间线；若未查到相关日志则为 None。
    """

    timeline: DocumentWorkflowTimelineResult | None = None


class GetDocumentExecutionTimelineToolOutput(OperationsToolResult):
    """文档执行时间线查询响应输出。

    Attributes:
        timeline: 文档全生命周期执行事件时间线。
    """

    timeline: DocumentExecutionTimelineResult | None = None


class GetDocumentFailureTimelineToolOutput(OperationsToolResult):
    """文档失败时间线查询响应输出。

    Attributes:
        timeline: 文档失败事件与错误摘要时间线。
    """

    timeline: DocumentFailureTimelineResult | None = None


class QueryAgentToolAuditsToolOutput(OperationsToolResult):
    """Agent Tool 审计事件查询响应输出。

    Attributes:
        audits: 匹配的 Tool 审计事件列表。
        next_cursor: 分页游标。
    """

    audits: list[AgentToolAuditEvent] = Field(default_factory=list)
    next_cursor: str | None = None


class ToolTimelineToolOutput(OperationsToolResult):
    """Tool 调用聚合时间线响应输出。

    Attributes:
        identifier: 查询的目标标识（task_id 或 agent_run_id）。
        invocations: 配对聚合后的 Tool 调用时间线列表（包含开始、结束、耗时与结果码）。
        truncated: 是否因达到 limit 上限而被截断。
    """

    identifier: str
    invocations: list[ToolInvocationTimelineItem] = Field(default_factory=list)
    truncated: bool = False
