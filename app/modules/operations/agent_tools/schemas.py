"""Operations Function Tool Schema。"""

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
    DateRangeQuery,
    ToolInvocationTimelineItem,
)


class QueryDocumentBusinessLogsToolInput(DocumentBusinessLogQuery):
    """文档业务日志查询输入。"""


class GetDocumentExecutionTimelineToolInput(DocumentTimelineQuery):
    """文档执行时间线输入。"""


class GetDocumentFailureTimelineToolInput(DocumentTimelineQuery):
    """文档失败时间线输入。"""


class QueryAgentToolAuditsToolInput(AgentToolAuditQuery):
    """Agent Tool 审计查询输入。"""


class ToolTimelineToolInput(DateRangeQuery):
    agent_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    created_from: datetime | None = None
    created_to: datetime | None = None
    limit: int = Field(default=500, ge=1, le=500)


class GetTaskToolTimelineToolInput(ToolTimelineToolInput):
    task_id: str = Field(min_length=1, max_length=200)


class GetAgentRunToolTimelineToolInput(ToolTimelineToolInput):
    agent_run_id: str = Field(min_length=1, max_length=200)


class OperationsToolResult(BaseModel):
    outcome: Literal["succeeded", "rejected", "failed"]
    result_code: str
    message: str
    retryable: bool
    resource_refs: list[str]


class QueryDocumentBusinessLogsToolOutput(OperationsToolResult):
    events: list[DocumentBusinessLogEvent] = Field(default_factory=list)
    next_cursor: str | None = None


class GetDocumentExecutionTimelineToolOutput(OperationsToolResult):
    timeline: DocumentExecutionTimelineResult | None = None


class GetDocumentFailureTimelineToolOutput(OperationsToolResult):
    timeline: DocumentFailureTimelineResult | None = None


class QueryAgentToolAuditsToolOutput(OperationsToolResult):
    audits: list[AgentToolAuditEvent] = Field(default_factory=list)
    next_cursor: str | None = None


class ToolTimelineToolOutput(OperationsToolResult):
    identifier: str
    invocations: list[ToolInvocationTimelineItem] = Field(default_factory=list)
    truncated: bool = False
