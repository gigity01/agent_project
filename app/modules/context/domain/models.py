"""Context 领域模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.context.domain.enums import ContextRouteMode


class ContextResourceRef(BaseModel):
    """数据库与 Redis 热队列共享的紧凑资源引用。"""

    resource_key: str
    resource_type: str
    resource_id: str
    relation: str | None = None
    summary: str | None = None
    source_turn_id: str
    last_seen_at: datetime


class ContextResourceQueue(BaseModel):
    """按最久未使用到最近使用排序的有界热资源队列。"""

    capacity: int = Field(ge=1)
    items: list[ContextResourceRef] = Field(default_factory=list)


class ConversationTurn(BaseModel):
    """一次完整用户输入及其唯一的下游处理结果。"""

    turn_id: str
    conversation_id: str
    user_input: str
    assistant_content: str | None = None
    assistant_compact: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    task_result_summary: str | None = None
    status: str
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ContextChainNode(BaseModel):
    """链与 Turn 的引用关系，不复制 Turn 原文。"""

    node_id: str
    chain_id: str
    turn_id: str
    sequence: int
    related_task_ids: list[str] = Field(default_factory=list)
    related_resource_refs: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class ContextChainNodeContext(ContextChainNode):
    """提供给 Agent 的已解析节点视图。"""

    turn: ConversationTurn


class ContextChain(BaseModel):
    """按顺序加载的完整上下文链。"""

    chain_id: str
    conversation_id: str
    nodes: list[ContextChainNodeContext]
    resource_queue: ContextResourceQueue
    last_active_at: datetime
    archived: bool = False


class ContextRouteDecision(BaseModel):
    """Context Agent 唯一允许返回的结构化结果。"""

    model_config = ConfigDict(extra="forbid")

    selected_chain_ids: list[str]
    create_new_chain: bool
    route_mode: ContextRouteMode
    reason_summary: str = Field(min_length=1, max_length=1000)
