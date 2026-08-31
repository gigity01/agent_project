"""业务日志和 Tool 审计查询数据传输对象（DTO）。

定义面向应用层、用例层及探针工具的各类日志查询条件与结构化返回实体。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, PositiveInt, model_validator


class DateRangeQuery(BaseModel):
    """时间范围查询基类。

    Attributes:
        created_from: 起始时间戳（含）。
        created_to: 截止时间戳（含）。
    """

    created_from: datetime | None = None
    created_to: datetime | None = None

    @model_validator(mode="after")
    def validate_created_range(self) -> "DateRangeQuery":
        """校验时间区间的合法性，确保起始时间不晚于截止时间。"""
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from 不能晚于 created_to")
        return self


class DocumentBusinessLogQuery(DateRangeQuery):
    """文档业务流水日志多维查询参数。

    Attributes:
        workflow_ids: 工作流 ID 列表。
        operation_ids: 阶段操作 ID 列表。
        attempts: 重试序号列表。
        document_ids: 文档 ID 列表。
        doc_codes: 文档业务编码列表。
        kb_ids: 知识库 ID 列表。
        stages: 处理阶段过滤（如 upload, process, chunk, index）。
        events: 事件名过滤。
        phases: 阶段内子阶段过滤。
        levels: 日志级别过滤（如 info, warning, error）。
        trace_id: 分布式追踪 ID。
        task_id: 关联的任务 ID。
        failed_only: 是否仅查询失败相关事件。
        limit: 单页拉取上限（1-500，默认 100）。
        cursor: 分页游标。
    """

    workflow_ids: list[str] = Field(default_factory=list)
    operation_ids: list[str] = Field(default_factory=list)
    attempts: list[PositiveInt] = Field(default_factory=list)
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
    """单篇文档生命周期或失败时间线查询参数。

    Attributes:
        document_id: 目标文档 ID。
        limit: 最大返回条数（1-500，默认 500）。
    """

    document_id: int = Field(gt=0)
    limit: int = Field(default=500, ge=1, le=500)


class DocumentOperationTimelineQuery(DateRangeQuery):
    """单次操作（operation_id）事件时间线查询参数。

    Attributes:
        operation_id: 目标操作 ID。
        limit: 最大返回条数（1-500，默认 500）。
    """

    operation_id: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=500, ge=1, le=500)


class DocumentWorkflowTimelineQuery(DateRangeQuery):
    """完整工作流（workflow_id）事件时间线查询参数。

    Attributes:
        workflow_id: 目标工作流 ID。
        limit: 最大返回条数（1-500，默认 500）。
    """

    workflow_id: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=500, ge=1, le=500)


class AgentToolAuditQuery(DateRangeQuery):
    """Agent Tool 调用审计多维查询参数。

    Attributes:
        trace_id: 链路追踪 ID。
        agent_run_id: Agent Run 运行会话 ID。
        conversation_id: 会话 ID。
        turn_id: 交互轮次 ID。
        task_id: 关联的 Task ID。
        agent_names: Agent 名称过滤列表。
        tool_names: Tool 名称过滤列表。
        actor_code: 执行主体代码。
        result_codes: 结果码过滤列表。
        retryable: 是否可重试过滤。
        events: 审计事件类型过滤。
        limit: 最大查询条数（1-500，默认 100）。
        cursor: 分页游标。
    """

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
    """特定实体（Task 或 Agent Run）下的 Tool 调用时间线查询参数。

    Attributes:
        identifier: 目标标识符（task_id 或 agent_run_id）。
        agent_names: Agent 名称列表。
        tool_names: Tool 名称列表。
        limit: 最大返回条数（1-500，默认 500）。
    """

    identifier: str = Field(min_length=1, max_length=200)
    agent_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    limit: int = Field(default=500, ge=1, le=500)


class JsonlScanPage(BaseModel):
    """底层 JSONL 扫描器返回的原始字典分页对象。

    Attributes:
        events: 原始事件字典列表。
        next_cursor: 下一页游标字符串。
    """

    events: list[dict[str, Any]]
    next_cursor: str | None


class DocumentBusinessLogEvent(BaseModel):
    """文档业务流水日志事件结构化实体。

    Attributes:
        event_id: 事件全局唯一标识。
        workflow_id: 关联的工作流 ID。
        operation_id: 关联的操作 ID。
        parent_operation_id: 父级操作 ID。
        attempt: 当前操作的重试尝试序号。
        document_id: 文档数据库主键 ID。
        doc_code: 文档业务编码。
        kb_id: 知识库主键 ID。
        stage: 处理阶段（如 upload, process, chunk, index）。
        event: 细粒度事件名称。
        phase: 阶段内子步骤。
        level: 日志级别（info, warning, error 等）。
        message: 文本消息。
        error_type: 异常类型名称。
        error_summary: 异常简要信息。
        status_before: 操作前文档状态。
        status_after: 操作后文档状态。
        state_updated: 文档状态是否发生变更。
        duration_ms: 耗时毫秒数。
        created_at: 日志记录时间戳。
        details: 额外扩展字段字典。
    """

    event_id: str
    workflow_id: str | None = None
    operation_id: str | None = None
    parent_operation_id: str | None = None
    attempt: int | None = None
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
    duration_ms: int = 0
    created_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class DocumentBusinessLogPage(BaseModel):
    """文档业务日志分页结果集。

    Attributes:
        items: 文档业务日志实体列表。
        next_cursor: 分页游标。
    """

    items: list[DocumentBusinessLogEvent]
    next_cursor: str | None


class DocumentExecutionTimelineResult(BaseModel):
    """文档全生命周期执行时间线聚合结果。

    Attributes:
        document_id: 目标文档 ID。
        events: 按时间升序排列的业务日志事件列表。
        truncated: 是否因达到 limit 上限而被截断。
    """

    document_id: int
    events: list[DocumentBusinessLogEvent]
    truncated: bool


class DocumentOperationTimelineResult(BaseModel):
    """单次文档操作（operation_id）时间线聚合结果。

    Attributes:
        operation_id: 操作唯一标识。
        workflow_id: 关联的工作流 ID。
        attempt: 操作重试次数。
        events: 该操作下的事件序列。
        truncated: 是否发生截断。
    """

    operation_id: str
    workflow_id: str | None
    attempt: int | None
    events: list[DocumentBusinessLogEvent]
    truncated: bool


class DocumentWorkflowTimelineResult(BaseModel):
    """完整文档工作流（workflow_id）时间线聚合结果。

    Attributes:
        workflow_id: 工作流唯一标识。
        events: 跨阶段事件序列。
        truncated: 是否发生截断。
    """

    workflow_id: str
    events: list[DocumentBusinessLogEvent]
    truncated: bool


class DocumentFailureEvent(BaseModel):
    """文档失败事件摘要实体。

    Attributes:
        event_id: 事件 ID。
        stage: 失败发生的阶段。
        event: 失败事件名。
        phase: 发生失败的子步骤。
        error_type: 异常类型。
        error_summary: 错误摘要。
        status_before: 失败前状态。
        status_after: 失败后状态。
        state_updated: 状态是否更新。
        created_at: 发生时间。
    """

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
    """文档失败时间线聚合结果。

    Attributes:
        document_id: 目标文档 ID。
        failures: 失败事件列表。
        truncated: 是否发生截断。
    """

    document_id: int
    failures: list[DocumentFailureEvent]
    truncated: bool


class AgentToolAuditEvent(BaseModel):
    """Agent Tool 调用审计事件实体。

    Attributes:
        event_id: 审计事件 ID。
        invocation_id: Tool 单次调用唯一标识。
        event: 审计事件类型（started, succeeded, failed, rejected）。
        trace_id: 链路追踪 ID。
        agent_run_id: Agent Run 运行会话 ID。
        conversation_id: 会话 ID。
        turn_id: 轮次 ID。
        task_id: 关联任务 ID。
        agent_name: 执行的 Agent 名称。
        tool_name: 调用的 Tool 名称。
        actor_code: 执行主体代码。
        resource_refs: 涉及的资源引用标识列表。
        duration_ms: 调用耗时毫秒数。
        result_code: 结果码。
        retryable: 是否可重试。
        created_at: 记录时间戳。
    """

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
    """Agent Tool 审计分页结果集。

    Attributes:
        items: 审计事件列表。
        next_cursor: 分页游标。
    """

    items: list[AgentToolAuditEvent]
    next_cursor: str | None


class ToolInvocationTimelineItem(BaseModel):
    """配对聚合后的单次 Tool 完整调用生命周期条目。

    合并了 started 事件与终端（succeeded/rejected/failed）事件。

    Attributes:
        invocation_id: 调用标识。
        trace_id: 链路追踪 ID。
        agent_run_id: Agent Run ID。
        conversation_id: 会话 ID。
        turn_id: 轮次 ID。
        task_id: 任务 ID。
        agent_name: Agent 名称。
        tool_name: Tool 名称。
        actor_code: 执行主体。
        resource_refs: 涉及资源。
        started_at: 开始调用时间。
        completed_at: 调用完成时间。
        outcome: 终态结果（succeeded, rejected, failed 等）。
        result_code: 结果码。
        retryable: 是否可重试。
        duration_ms: 总耗时（毫秒）。
    """

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
    """实体级别（Task / Agent Run）Tool 调用聚合时间线结果。

    Attributes:
        identifier: 查询标识（task_id 或 agent_run_id）。
        invocations: 配对后的 Tool 调用条目列表。
        truncated: 是否发生截断。
    """

    identifier: str
    invocations: list[ToolInvocationTimelineItem]
    truncated: bool
