"""Context Agent、上下文链和 Turn 的结构化契约。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ContextResources(BaseModel):
    """一条上下文链当前关联的完整资源集合。"""

    document_ids: list[int] = Field(default_factory=list)
    document_codes: list[str] = Field(default_factory=list)
    knowledge_base_ids: list[int] = Field(default_factory=list)
    plan_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    result_refs: list[str] = Field(default_factory=list)
    other: dict[str, list[str]] = Field(default_factory=dict)


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
    resources: ContextResources
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

    selected_chain_ids: list[str] = Field(default_factory=list)
    create_new_chain: bool = False
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
    """下游完成后写入某条链的关联元数据与资源快照。"""

    chain_id: str = Field(min_length=1, max_length=100)
    related_task_ids: list[str] = Field(default_factory=list)
    related_resource_refs: list[str] = Field(default_factory=list)
    resources: ContextResources | None = None


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
