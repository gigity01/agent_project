"""Context 领域模型定义。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContextResourceRef(BaseModel):
    """数据库与 Redis 热队列共享的紧凑资源引用模型。

    Attributes:
        resource_key: 资源唯一标识键（例如 "document:doc_123"）。
        resource_type: 资源类型（例如 "document"）。
        resource_id: 业务资源实体 ID。
        relation: 资源与上下文的关系说明（如 "task_output", "user_reference"）。
        summary: 资源简要描述。
        source_turn_id: 首次引入该资源的 Turn ID。
        last_seen_at: 最近一次在链中被使用的时间戳。
    """

    resource_key: str
    resource_type: str
    resource_id: str
    relation: str | None = None
    summary: str | None = None
    source_turn_id: str
    last_seen_at: datetime


class ContextResourceQueue(BaseModel):
    """按最久未使用到最近使用排序的有界热资源队列（刷新式 FIFO）。

    Attributes:
        capacity: 队列容量上限（默认 16）。
        items: 资源引用列表（队尾为最新使用，队头为最旧未再使用）。
    """

    capacity: int = Field(ge=1)
    items: list[ContextResourceRef] = Field(default_factory=list)


class ConversationTurn(BaseModel):
    """一次完整用户输入及其唯一的下游处理结果领域模型。

    Attributes:
        turn_id: 轮次唯一标识。
        conversation_id: 所属会话 ID。
        user_input: 用户原始输入文本。
        assistant_content: 助手完整回答文本。
        assistant_compact: 紧凑版历史摘要（用于长上下文修剪压缩）。
        clarification_input: 用户对澄清问题的补充回答文本。
        task_ids: 本轮规划并执行的 Task ID 列表。
        task_result_summary: 任务执行结果的事实摘要。
        status: Turn 生命周期状态（ContextTurnStatus）。
        created_at: 创建时间。
        completed_at: 完成时间。
    """

    turn_id: str
    conversation_id: str
    user_input: str
    assistant_content: str | None = None
    assistant_compact: str | None = None
    clarification_input: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    task_result_summary: str | None = None
    status: str
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ContextChainNode(BaseModel):
    """链与 Turn 的关联节点领域模型（仅引用 Turn，不复制文本）。

    Attributes:
        node_id: 节点唯一主键 ID。
        chain_id: 所属上下文链 ID。
        turn_id: 引用的 Turn ID。
        sequence: 在链内的严格递增序号（从 1 开始）。
        related_task_ids: 在该链上下文中涉及的任务 ID 列表。
        related_resource_refs: 本轮在链中涉及的资源 Key 列表。
        created_at: 节点创建时间。
    """

    node_id: str
    chain_id: str
    turn_id: str
    sequence: int
    related_task_ids: list[str] = Field(default_factory=list)
    related_resource_refs: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class ContextChainNodeContext(ContextChainNode):
    """包含已解析 Turn 详情的节点完整视图（供 Agent 读取）。

    Attributes:
        turn: 关联解析出的 ConversationTurn 领域对象。
    """

    turn: ConversationTurn


class ContextChain(BaseModel):
    """完整上下文链领域模型。

    Attributes:
        chain_id: 上下文链唯一标识。
        conversation_id: 所属会话 ID。
        nodes: 按序号升序排列的节点列表（包含对应 Turn）。
        resource_queue: 当前链的热资源刷新式 FIFO 队列。
        last_active_at: 最近活跃时间。
        archived: 是否已归档。
    """

    chain_id: str
    conversation_id: str
    nodes: list[ContextChainNodeContext]
    resource_queue: ContextResourceQueue
    last_active_at: datetime
    archived: bool = False


class ContextSelectionDecision(BaseModel):
    """Context Agent 做出的历史读取集合路由决策。

    Attributes:
        relevant_chain_ids: 命中的历史上下文链 ID 列表（Read Set）。
        reason_summary: 路由决策的理由说明。
    """

    model_config = ConfigDict(extra="forbid")

    relevant_chain_ids: list[str]
    reason_summary: str = Field(min_length=1, max_length=1000)
