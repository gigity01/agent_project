"""Context 只读查询条件与结果 DTO。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeRangeQuery(BaseModel):
    created_from: datetime | None = None
    created_to: datetime | None = None

    @model_validator(mode="after")
    def validate_created_range(self) -> "TimeRangeQuery":
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from 不能晚于 created_to")
        return self


class ConversationTurnSearchQuery(TimeRangeQuery):
    conversation_id: str | None = Field(default=None, max_length=100)
    turn_ids: list[str] = Field(default_factory=list)
    turn_statuses: list[str] = Field(default_factory=list)
    completed_from: datetime | None = None
    completed_to: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_completed_range(self) -> "ConversationTurnSearchQuery":
        if (
            self.completed_from is not None
            and self.completed_to is not None
            and self.completed_from > self.completed_to
        ):
            raise ValueError("completed_from 不能晚于 completed_to")
        return self


class ContextChainSearchQuery(TimeRangeQuery):
    conversation_id: str | None = Field(default=None, max_length=100)
    chain_ids: list[str] = Field(default_factory=list)
    archived: bool | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ContextChainNodeSearchQuery(TimeRangeQuery):
    conversation_id: str | None = Field(default=None, max_length=100)
    chain_id: str | None = Field(default=None, max_length=100)
    chain_ids: list[str] = Field(default_factory=list)
    turn_id: str | None = Field(default=None, max_length=100)
    turn_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ContextChainResourceSearchQuery(BaseModel):
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
        if (
            self.last_seen_from is not None
            and self.last_seen_to is not None
            and self.last_seen_from > self.last_seen_to
        ):
            raise ValueError("last_seen_from 不能晚于 last_seen_to")
        return self


class ContextRouteRecordSearchQuery(TimeRangeQuery):
    conversation_id: str | None = Field(default=None, max_length=100)
    turn_id: str | None = Field(default=None, max_length=100)
    route_modes: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ConversationTurnQueryResult(BaseModel):
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
    chain_id: str
    conversation_id: str
    resource_version: int
    last_active_at: datetime
    archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContextChainNodeQueryResult(BaseModel):
    node_id: str
    chain_id: str
    turn_id: str
    sequence: int
    related_task_ids: list[str]
    related_resource_refs: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContextChainResourceQueryResult(BaseModel):
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


class ContextRouteRecordQueryResult(BaseModel):
    route_id: str
    conversation_id: str
    current_turn_id: str
    selected_chain_ids: list[str]
    create_new_chain: bool
    route_mode: str
    reason_summary: str
    new_chain_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationTurnListResult(BaseModel):
    items: list[ConversationTurnQueryResult]
    total: int
    limit: int
    offset: int


class ContextChainListResult(BaseModel):
    items: list[ContextChainQueryResult]
    total: int
    limit: int
    offset: int


class ContextChainNodeListResult(BaseModel):
    items: list[ContextChainNodeQueryResult]
    total: int
    limit: int
    offset: int


class ContextChainResourceListResult(BaseModel):
    items: list[ContextChainResourceQueryResult]
    total: int
    limit: int
    offset: int


class ContextRouteRecordListResult(BaseModel):
    items: list[ContextRouteRecordQueryResult]
    total: int
    limit: int
    offset: int
