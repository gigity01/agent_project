"""Context HTTP 请求与响应模型定义。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.context.domain.models import (
    ContextChain,
    ContextSelectionDecision,
    ConversationTurn,
)


class ContextSelectionRequest(BaseModel):
    """旧路径上的 Context Selection 兼容请求模型。

    Attributes:
        conversation_id: 会话唯一标识。
        user_input: 用户输入的原始文本。
    """

    conversation_id: str = Field(min_length=1, max_length=100)
    user_input: str = Field(min_length=1)


class SelectedContextPackage(BaseModel):
    """旧路径上的 Context Selection 兼容响应模型。

    Attributes:
        current_turn_id: 本轮分配的 Turn ID。
        current_user_input: 用户原始输入文本。
        context_chains: 命中的上下文链列表（包含节点与资源）。
        selection_decision: Context Agent 路由选择决策。
    """

    current_turn_id: str
    current_user_input: str
    context_chains: list[ContextChain]
    selection_decision: ContextSelectionDecision


class ContextResourceInput(BaseModel):
    """下游提交的单个资源事实输入模型。

    Attributes:
        resource_type: 资源类型（如 "document"）。
        resource_id: 资源业务标识。
        relation: 关联关系描述。
        summary: 资源简要说明。
    """

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
        """获取规范的 resource_key。"""
        return f"{self.resource_type}:{self.resource_id}"


class ContextChainTurnUpdate(BaseModel):
    """下游完成后写入某条链的本轮资源更新载荷模型。

    Attributes:
        chain_id: 目标上下文链 ID。
        related_task_ids: 本轮关联的任务 ID 列表。
        related_resources: 本轮引入或更新的资源列表。
        removed_resource_keys: 本轮显式停用或移除的资源 Key 列表。
    """

    chain_id: str = Field(min_length=1, max_length=100)
    related_task_ids: list[str] = Field(default_factory=list)
    related_resources: list[ContextResourceInput] = Field(
        default_factory=list
    )
    removed_resource_keys: list[str] = Field(default_factory=list)


class ContextTurnAttribution(BaseModel):
    """完成阶段提交的最终 Chain 写入归属集合模型。

    Attributes:
        existing_chain_ids: 需关联归因的已有链 ID 列表。
        create_new_chain: 是否需要创建新链。
        new_chain_id: 预分配的新链 ID（可选）。
    """

    existing_chain_ids: list[str] = Field(default_factory=list)
    create_new_chain: bool = False
    new_chain_id: str | None = Field(default=None, min_length=1, max_length=100)


class CompleteContextTurnRequest(BaseModel):
    """下游完成处理后补全唯一 Turn 并正式关联全部目标链的请求体模型。

    Attributes:
        assistant_content: 助手完整文本。
        assistant_compact: 紧凑摘要。
        task_ids: 本轮执行的任务 ID 列表。
        task_result_summary: 任务结果摘要。
        attribution: 最终链归属配置。
        chain_updates: 针对目标链的节点与资源更新列表。
    """

    assistant_content: str | None = None
    assistant_compact: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    task_result_summary: str | None = None
    attribution: ContextTurnAttribution = Field(
        default_factory=ContextTurnAttribution
    )
    chain_updates: list[ContextChainTurnUpdate] = Field(default_factory=list)


class CompleteContextTurnResponse(BaseModel):
    """Turn 完成回写后的关联结果响应模型。

    Attributes:
        turn: 完成后的 ConversationTurn 领域对象。
        linked_chain_ids: 最终关联建立节点的所有上下文链 ID 列表。
    """

    turn: ConversationTurn
    linked_chain_ids: list[str]
