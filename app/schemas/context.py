"""Context Agent、上下文链和 Turn 的结构化契约。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ContextResourceInput(BaseModel):
    """下游提交的单个资源事实，不包含完整业务对象。"""

    resource_type: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    resource_id: str = Field(min_length=1, max_length=400)
    relation: str | None = Field(default=None, max_length=100)
    summary: str | None = Field(default=None, max_length=1000)

    @property
    def resource_key(self) -> str:
        return f"{self.resource_type}:{self.resource_id}"


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


class ContextAgentInput(BaseModel):
    """Context Agent 单次路由所需的全部输入。"""

    conversation_id: str
    current_turn_id: str
    current_user_input: str
    chains: list[ContextChain]


class ContextRouteMode(str, Enum):
    SINGLE_MATCH = "single_match"
    MULTI_MATCH = "multi_match"
    NEW_CHAIN = "new_chain"
    EXISTING_AND_NEW = "existing_and_new"
    FALLBACK_LATEST = "fallback_latest"


class ContextRouteDecision(BaseModel):
    """Context Agent 唯一允许返回的结构化结果。"""

    model_config = ConfigDict(extra="forbid")

    selected_chain_ids: list[str]
    create_new_chain: bool
    route_mode: ContextRouteMode
    reason_summary: str = Field(min_length=1, max_length=1000)


class RoutedContextPackage(BaseModel):
    """交给下一个 Agent 的完整上下文包。"""

    current_turn_id: str
    current_user_input: str
    selected_chains: list[ContextChain]
    new_chain_id: str | None = None
    route_decision: ContextRouteDecision


class ContextRouteRequest(BaseModel):
    """创建 Turn 并发起上下文路由的请求。"""

    conversation_id: str = Field(min_length=1, max_length=100)
    user_input: str = Field(min_length=1)


class ContextChainTurnUpdate(BaseModel):
    """下游完成后写入某条链的本轮资源事实。"""

    chain_id: str = Field(min_length=1, max_length=100)
    related_task_ids: list[str] = Field(default_factory=list)
    related_resources: list[ContextResourceInput] = Field(
        default_factory=list
    )
    removed_resource_keys: list[str] = Field(default_factory=list)


class CompleteContextTurnRequest(BaseModel):
    """下游完成处理后补全唯一 Turn 并正式关联全部目标链。"""

    assistant_content: str | None = None
    assistant_compact: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    task_result_summary: str | None = None
    chain_updates: list[ContextChainTurnUpdate] = Field(default_factory=list)


class CompleteContextTurnResponse(BaseModel):
    """Turn 完成回写后的关联结果。"""

    turn: ConversationTurn
    linked_chain_ids: list[str]
