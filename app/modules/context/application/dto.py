"""Context Application 层命令、结果与内部契约。"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.modules.context.domain.models import (
    ContextChain,
    ContextSelectionDecision,
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
class ContextSelectionResult:
    """消息完成历史 Context Selection 后的应用结果。"""

    conversation_id: str
    turn_id: str
    message: str
    context_chains: list[ContextChain]
    decision: ContextSelectionDecision

    @property
    def context_chain_ids(self) -> list[str]:
        return [chain.chain_id for chain in self.context_chains]


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
    """下游对一条最终归属 Chain 的本轮更新。"""

    chain_id: str
    related_task_ids: list[str] = field(default_factory=list)
    related_resources: list[ContextResourceInput] = field(
        default_factory=list
    )
    removed_resource_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnAttribution:
    """当前 Turn 的最终 Chain 写入集合。"""

    existing_chain_ids: list[str] = field(default_factory=list)
    create_new_chain: bool = False
    # 完成方可预分配新 Chain ID，以便同一事务内提交该 Chain 的资源更新。
    new_chain_id: str | None = None


@dataclass(frozen=True)
class CompleteTurnCommand:
    """完成 Context Turn 的应用命令。"""

    assistant_content: str | None = None
    assistant_compact: str | None = None
    task_ids: list[str] = field(default_factory=list)
    task_result_summary: str | None = None
    attribution: TurnAttribution = field(default_factory=TurnAttribution)
    chain_updates: list[ChainTurnUpdate] = field(default_factory=list)


@dataclass(frozen=True)
class CompleteTurnResult:
    """Context Turn 完成后的应用结果。"""

    turn: ConversationTurn
    linked_chain_ids: list[str]
