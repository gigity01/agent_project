"""业务日志和 Tool 审计查询 DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, PositiveInt, model_validator


class DateRangeQuery(BaseModel):
    created_from: datetime | None = None
    created_to: datetime | None = None

    @model_validator(mode="after")
    def validate_created_range(self) -> "DateRangeQuery":
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from 不能晚于 created_to")
        return self


class DocumentBusinessLogQuery(DateRangeQuery):
    document_ids: list[PositiveInt] = Field(default_factory=list)
    doc_codes: list[str] = Field(default_factory=list)
    kb_ids: list[PositiveInt] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    levels: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    task_id: str | None = None
    failed_only: bool = False
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = Field(default=None, max_length=2048)


class DocumentTimelineQuery(DateRangeQuery):
    document_id: int = Field(gt=0)
    limit: int = Field(default=500, ge=1, le=500)


class AgentToolAuditQuery(DateRangeQuery):
    trace_id: str | None = None
    agent_run_id: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
    task_id: str | None = None
    agent_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    actor_code: str | None = None
    result_codes: list[str] = Field(default_factory=list)
    retryable: bool | None = None
    events: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = Field(default=None, max_length=2048)


class ToolTimelineQuery(DateRangeQuery):
    identifier: str = Field(min_length=1, max_length=200)
    agent_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    limit: int = Field(default=500, ge=1, le=500)


class JsonlScanPage(BaseModel):
    events: list[dict[str, Any]]
    next_cursor: str | None


class DocumentBusinessLogEvent(BaseModel):
    event_id: str
    run_id: str | None
    document_id: int | None
    doc_code: str | None
    kb_id: int | None
    stage: str
    event: str
    phase: str | None
    level: str | None
    message: str | None
    error_type: str | None
    error_summary: str | None
    status_before: str | None
    status_after: str | None
    state_updated: bool | None
    created_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class DocumentBusinessLogPage(BaseModel):
    items: list[DocumentBusinessLogEvent]
    next_cursor: str | None


class DocumentExecutionTimelineResult(BaseModel):
    document_id: int
    events: list[DocumentBusinessLogEvent]
    truncated: bool


class DocumentFailureEvent(BaseModel):
    event_id: str
    stage: str
    event: str
    phase: str | None
    error_type: str | None
    error_summary: str | None
    status_before: str | None
    status_after: str | None
    state_updated: bool | None
    created_at: datetime


class DocumentFailureTimelineResult(BaseModel):
    document_id: int
    failures: list[DocumentFailureEvent]
    truncated: bool


class AgentToolAuditEvent(BaseModel):
    event_id: str
    invocation_id: str
    event: str
    trace_id: str
    agent_run_id: str
    conversation_id: str | None
    turn_id: str | None
    task_id: str | None
    agent_name: str
    tool_name: str
    actor_code: str
    resource_refs: list[str]
    duration_ms: int
    result_code: str | None
    retryable: bool | None
    created_at: datetime


class AgentToolAuditPage(BaseModel):
    items: list[AgentToolAuditEvent]
    next_cursor: str | None


class ToolInvocationTimelineItem(BaseModel):
    invocation_id: str
    trace_id: str
    agent_run_id: str
    conversation_id: str | None
    turn_id: str | None
    task_id: str | None
    agent_name: str
    tool_name: str
    actor_code: str
    resource_refs: list[str]
    started_at: datetime
    completed_at: datetime | None
    outcome: str | None
    result_code: str | None
    retryable: bool | None
    duration_ms: int | None


class ToolTimelineResult(BaseModel):
    identifier: str
    invocations: list[ToolInvocationTimelineItem]
    truncated: bool
