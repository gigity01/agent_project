"""Context Application 层命令、结果与内部契约。"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.modules.context.domain.models import (
    ContextChain,
    ContextRouteDecision,
    ConversationTurn,
)


class ContextAgentInput(BaseModel):
    """Context Router 单次路由所需的全部后端输入。"""

    conversation_id: str
    current_turn_id: str
    current_user_input: str
    chains: list[ContextChain]


@dataclass(frozen=True)
class SendMessageCommand:
    """发送一条 Conversation Message。"""

    conversation_id: str
    message: str


@dataclass(frozen=True)
class RouteContextResult:
    """消息完成 Context 路由后的应用结果。"""

    conversation_id: str
    turn_id: str
    message: str
    selected_chains: list[ContextChain]
    new_chain_id: str | None
    decision: ContextRouteDecision

    @property
    def selected_chain_ids(self) -> list[str]:
        return [chain.chain_id for chain in self.selected_chains]

    @property
    def current_turn_id(self) -> str:
        """兼容旧内部调用使用的字段名。"""
        return self.turn_id

    @property
    def current_user_input(self) -> str:
        """兼容旧内部调用使用的字段名。"""
        return self.message

    @property
    def route_decision(self) -> ContextRouteDecision:
        """兼容旧内部调用使用的字段名。"""
        return self.decision


@dataclass(frozen=True)
class ContextResourceInput:
    """下游提交的单个资源事实。"""

    resource_type: str
    resource_id: str
    relation: str | None = None
    summary: str | None = None

    @property
    def resource_key(self) -> str:
        return f"{self.resource_type}:{self.resource_id}"


@dataclass(frozen=True)
class ChainTurnUpdate:
    """下游对一条已路由 Chain 的本轮更新。"""

    chain_id: str
    related_task_ids: list[str] = field(default_factory=list)
    related_resources: list[ContextResourceInput] = field(
        default_factory=list
    )
    removed_resource_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompleteTurnCommand:
    """完成 Context Turn 的应用命令。"""

    assistant_content: str | None = None
    assistant_compact: str | None = None
    task_ids: list[str] = field(default_factory=list)
    task_result_summary: str | None = None
    chain_updates: list[ChainTurnUpdate] = field(default_factory=list)


@dataclass(frozen=True)
class CompleteTurnResult:
    """Context Turn 完成后的应用结果。"""

    turn: ConversationTurn
    linked_chain_ids: list[str]
