"""Context Application 层命令、结果与内部契约 DTO 定义。"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.modules.context.domain.models import (
    ContextChain,
    ContextSelectionDecision,
    ConversationTurn,
)


class ContextAgentInput(BaseModel):
    """Context Agent 单次历史 Read Set 选择所需的完整输入。

    Attributes:
        conversation_id: 会话唯一标识。
        current_turn_id: 本轮交互对应的 Turn ID。
        current_user_input: 用户原始输入消息文本。
        chains: 当前会话的所有未归档上下文链（已注入热资源队列）。
    """

    conversation_id: str
    current_turn_id: str
    current_user_input: str
    chains: list[ContextChain]


@dataclass(frozen=True)
class SendMessageCommand:
    """发送一条 Conversation Message 的应用层命令。

    Attributes:
        conversation_id: 会话唯一标识。
        message: 用户输入的原始文本。
    """

    conversation_id: str
    message: str


@dataclass(frozen=True)
class ContextSelectionResult:
    """消息完成历史 Context Selection 后的应用层结果。

    Attributes:
        conversation_id: 会话唯一标识。
        turn_id: 创建并推进至 context_ready 状态的 Turn ID。
        message: 用户原始输入文本。
        context_chains: 命中的上下文链领域对象列表。
        decision: Context Agent 产出的历史 Read Set 选择。
    """

    conversation_id: str
    turn_id: str
    message: str
    context_chains: list[ContextChain]
    decision: ContextSelectionDecision

    @property
    def context_chain_ids(self) -> list[str]:
        """获取命中的上下文链 ID 列表。"""
        return [chain.chain_id for chain in self.context_chains]


@dataclass(frozen=True)
class ContextResourceInput:
    """下游提交的单个资源事实输入 DTO。

    Attributes:
        resource_type: 资源类型（如 "document"）。
        resource_id: 资源业务标识。
        relation: 资源关系类型（如 "task_output"）。
        summary: 资源简要说明。
    """

    resource_type: str
    resource_id: str
    relation: str | None = None
    summary: str | None = None

    @property
    def resource_key(self) -> str:
        """获取标准的 resource_key（格式为 `resource_type:resource_id`）。"""
        return f"{self.resource_type}:{self.resource_id}"


@dataclass(frozen=True)
class ChainTurnUpdate:
    """下游对一条最终归属 Chain 的本轮更新载荷。

    Attributes:
        chain_id: 目标上下文链 ID。
        related_task_ids: 本轮在该链中执行的任务 ID 列表。
        related_resources: 本轮引入或引用的资源列表。
        removed_resource_keys: 本轮显式停用/移除的资源 Key 列表。
    """

    chain_id: str
    related_task_ids: list[str] = field(default_factory=list)
    related_resources: list[ContextResourceInput] = field(
        default_factory=list
    )
    removed_resource_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnAttribution:
    """当前 Turn 的最终上下文链归属（写入集合）。

    Attributes:
        existing_chain_ids: 需关联归因的已有链 ID 列表。
        create_new_chain: 是否需要创建一条新链。
        new_chain_id: 预分配的新链 ID（可在事务内一并提交该链的节点与资源更新）。
    """

    existing_chain_ids: list[str] = field(default_factory=list)
    create_new_chain: bool = False
    # 完成方可预分配新 Chain ID，以便同一事务内提交该 Chain 的资源更新。
    new_chain_id: str | None = None


@dataclass(frozen=True)
class CompleteTurnCommand:
    """完成 Context Turn 的应用层命令。

    Attributes:
        assistant_content: 助手完整回答文本。
        assistant_compact: 助手紧凑摘要文本。
        task_ids: 本轮执行的任务 ID 列表。
        task_result_summary: 任务结果摘要。
        attribution: 最终链归属（TurnAttribution）。
        chain_updates: 针对归属链的资源及节点更新列表。
    """

    assistant_content: str | None = None
    assistant_compact: str | None = None
    task_ids: list[str] = field(default_factory=list)
    task_result_summary: str | None = None
    attribution: TurnAttribution = field(default_factory=TurnAttribution)
    chain_updates: list[ChainTurnUpdate] = field(default_factory=list)


@dataclass(frozen=True)
class CompleteTurnResult:
    """Context Turn 完成后的应用层结果。

    Attributes:
        turn: 完成后的 ConversationTurn 领域对象。
        linked_chain_ids: 最终关联建立节点的所有上下文链 ID 列表。
    """

    turn: ConversationTurn
    linked_chain_ids: list[str]
