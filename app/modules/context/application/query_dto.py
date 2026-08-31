"""Context 只读查询条件与结果 DTO 定义。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeRangeQuery(BaseModel):
    """时间范围基础查询参数模型。

    Attributes:
        created_from: 创建起始时间（含）。
        created_to: 创建截止时间（含）。
    """

    created_from: datetime | None = None
    created_to: datetime | None = None

    @model_validator(mode="after")
    def validate_created_range(self) -> "TimeRangeQuery":
        """校验创建时间区间的合法性。"""
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from 不能晚于 created_to")
        return self


class ConversationTurnSearchQuery(TimeRangeQuery):
    """Conversation Turn 分页筛选查询参数。

    Attributes:
        conversation_id: 会话 ID 过滤条件。
        turn_ids: 待查询的 Turn ID 列表。
        turn_statuses: 状态过滤列表。
        completed_from: 完成时间起始（含）。
        completed_to: 完成时间截止（含）。
        limit: 每页条数上限（1~100，默认 50）。
        offset: 分页偏移量（>=0，默认 0）。
    """

    conversation_id: str | None = Field(default=None, max_length=100)
    turn_ids: list[str] = Field(default_factory=list)
    turn_statuses: list[str] = Field(default_factory=list)
    completed_from: datetime | None = None
    completed_to: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_completed_range(self) -> "ConversationTurnSearchQuery":
        """校验完成时间区间的合法性。"""
        if (
            self.completed_from is not None
            and self.completed_to is not None
            and self.completed_from > self.completed_to
        ):
            raise ValueError("completed_from 不能晚于 completed_to")
        return self


class ContextChainSearchQuery(TimeRangeQuery):
    """Context Chain 分页筛选查询参数。

    Attributes:
        conversation_id: 会话 ID 过滤。
        chain_ids: 链 ID 过滤列表。
        archived: 是否归档过滤。
        limit: 每页条数。
        offset: 分页偏移。
    """

    conversation_id: str | None = Field(default=None, max_length=100)
    chain_ids: list[str] = Field(default_factory=list)
    archived: bool | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ContextChainNodeSearchQuery(TimeRangeQuery):
    """Context Chain Node 分页筛选查询参数。

    Attributes:
        conversation_id: 会话 ID 过滤。
        chain_id: 单个链 ID 过滤。
        chain_ids: 链 ID 过滤列表。
        turn_id: 单个 Turn ID 过滤。
        turn_ids: Turn ID 过滤列表。
        limit: 每页条数。
        offset: 分页偏移。
    """

    conversation_id: str | None = Field(default=None, max_length=100)
    chain_id: str | None = Field(default=None, max_length=100)
    chain_ids: list[str] = Field(default_factory=list)
    turn_id: str | None = Field(default=None, max_length=100)
    turn_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ContextChainResourceSearchQuery(BaseModel):
    """Context Chain Resource 分页筛选查询参数。

    Attributes:
        conversation_id: 会话 ID。
        chain_id: 单个链 ID。
        chain_ids: 链 ID 列表。
        resource_type: 资源类型。
        resource_id: 资源业务标识。
        active: 是否有效（未被显式移除）。
        last_seen_from: 最近活跃时间起始。
        last_seen_to: 最近活跃时间截止。
        limit: 每页条数。
        offset: 分页偏移。
    """

    conversation_id: str | None = Field(default=None, max_length=100)
    chain_id: str | None = Field(default=None, max_length=100)
    chain_ids: list[str] = Field(default_factory=list)
    resource_type: str | None = Field(default=None, max_length=100)
    resource_id: str | None = Field(default=None, max_length=400)
    active: bool | None = None
    last_seen_from: datetime | None = None
    last_seen_to: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_last_seen_range(self) -> "ContextChainResourceSearchQuery":
        """校验最近活跃时间区间的合法性。"""
        if (
            self.last_seen_from is not None
            and self.last_seen_to is not None
            and self.last_seen_from > self.last_seen_to
        ):
            raise ValueError("last_seen_from 不能晚于 last_seen_to")
        return self


class ContextSelectionRecordSearchQuery(TimeRangeQuery):
    """Context SelectionRecord 分页筛选查询参数。

    Attributes:
        conversation_id: 会话 ID。
        turn_id: 关联的 Turn ID。
        selection_modes: 路由选择模式过滤列表。
        limit: 每页条数。
        offset: 分页偏移。
    """

    conversation_id: str | None = Field(default=None, max_length=100)
    turn_id: str | None = Field(default=None, max_length=100)
    selection_modes: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ConversationTurnQueryResult(BaseModel):
    """Conversation Turn 只读查询结果模型。"""

    turn_id: str
    conversation_id: str
    user_input: str
    assistant_content: str | None
    assistant_compact: str | None
    task_ids: list[str]
    task_result_summary: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ContextChainQueryResult(BaseModel):
    """Context Chain 只读查询结果模型。"""

    chain_id: str
    conversation_id: str
    resource_version: int
    last_active_at: datetime
    archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContextChainNodeQueryResult(BaseModel):
    """Context Chain Node 只读查询结果模型。"""

    node_id: str
    chain_id: str
    turn_id: str
    sequence: int
    related_task_ids: list[str]
    related_resource_refs: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContextChainResourceQueryResult(BaseModel):
    """Context Chain Resource 只读查询结果模型。"""

    id: int
    chain_id: str
    resource_key: str
    resource_type: str
    resource_id: str
    relation: str | None
    summary: str | None
    first_seen_turn_id: str
    last_seen_turn_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    use_count: int
    active: bool
    removed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ContextSelectionRecordQueryResult(BaseModel):
    """Context SelectionRecord 只读查询结果模型。"""

    selection_id: str
    conversation_id: str
    current_turn_id: str
    relevant_chain_ids: list[str]
    selection_mode: str
    reason_summary: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationTurnListResult(BaseModel):
    """Conversation Turn 分页查询结果包装。"""

    items: list[ConversationTurnQueryResult]
    total: int
    limit: int
    offset: int


class ContextChainListResult(BaseModel):
    """Context Chain 分页查询结果包装。"""

    items: list[ContextChainQueryResult]
    total: int
    limit: int
    offset: int


class ContextChainNodeListResult(BaseModel):
    """Context Chain Node 分页查询结果包装。"""

    items: list[ContextChainNodeQueryResult]
    total: int
    limit: int
    offset: int


class ContextChainResourceListResult(BaseModel):
    """Context Chain Resource 分页查询结果包装。"""

    items: list[ContextChainResourceQueryResult]
    total: int
    limit: int
    offset: int


class ContextSelectionRecordListResult(BaseModel):
    """Context SelectionRecord 分页查询结果包装。"""

    items: list[ContextSelectionRecordQueryResult]
    total: int
    limit: int
    offset: int
