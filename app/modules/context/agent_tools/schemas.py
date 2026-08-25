"""Context 只读 Function Tool 输入与输出 Schema 定义。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.context.application.query_dto import (
    ContextChainNodeQueryResult,
    ContextChainNodeSearchQuery,
    ContextChainQueryResult,
    ContextChainResourceQueryResult,
    ContextChainResourceSearchQuery,
    ContextChainSearchQuery,
    ContextSelectionRecordQueryResult,
    ContextSelectionRecordSearchQuery,
    ConversationTurnQueryResult,
    ConversationTurnSearchQuery,
)


class GetConversationTurnToolInput(BaseModel):
    """获取单个 Conversation Turn 工具输入。"""

    turn_id: str = Field(min_length=1, max_length=100, description="Turn 唯一标识")


class ListConversationTurnsToolInput(ConversationTurnSearchQuery):
    """查询 Conversation Turn 列表工具输入。"""


class GetContextChainToolInput(BaseModel):
    """获取单个 Context Chain 工具输入。"""

    chain_id: str = Field(min_length=1, max_length=100, description="上下文链唯一标识")


class ListContextChainsToolInput(ContextChainSearchQuery):
    """查询 Context Chain 列表工具输入。"""


class ListContextChainNodesToolInput(ContextChainNodeSearchQuery):
    """查询 Context Chain Node 列表工具输入。"""


class ListContextChainResourcesToolInput(ContextChainResourceSearchQuery):
    """查询 Context Chain Resource 列表工具输入。"""


class ListContextSelectionRecordsToolInput(ContextSelectionRecordSearchQuery):
    """查询 Context SelectionRecord 列表工具输入。"""


class ContextToolResult(BaseModel):
    """Context Tool 通用审计与执行结果 Envelope 基类。

    Attributes:
        outcome: 执行判定结果（succeeded / rejected / failed）。
        result_code: 结构化业务返回码。
        message: 结果或错误描述文本。
        retryable: 遇到失败时是否建议重试。
        resource_refs: 审计捕获的受影响/读取资源引用列表。
    """

    outcome: Literal["succeeded", "rejected", "failed"] = Field(description="工具执行判定结果")
    result_code: str = Field(description="结构化结果码")
    message: str = Field(description="描述信息")
    retryable: bool = Field(description="是否可重试")
    resource_refs: list[str] = Field(default_factory=list, description="涉及的资源引用列表")


class GetConversationTurnToolOutput(ContextToolResult):
    """获取单个 Conversation Turn 工具输出。"""

    turn: ConversationTurnQueryResult | None = Field(default=None, description="Turn 详细信息")


class ListConversationTurnsToolOutput(ContextToolResult):
    """查询 Conversation Turn 列表工具输出。"""

    turns: list[ConversationTurnQueryResult] = Field(default_factory=list, description="Turn 列表")
    total: int = Field(default=0, description="符合条件的总数")
    limit: int = Field(default=0, description="每页条数")
    offset: int = Field(default=0, description="分页偏移量")


class GetContextChainToolOutput(ContextToolResult):
    """获取单个 Context Chain 工具输出。"""

    chain: ContextChainQueryResult | None = Field(default=None, description="上下文链详细信息")


class ListContextChainsToolOutput(ContextToolResult):
    """查询 Context Chain 列表工具输出。"""

    chains: list[ContextChainQueryResult] = Field(default_factory=list, description="上下文链列表")
    total: int = Field(default=0, description="符合条件的总数")
    limit: int = Field(default=0, description="每页条数")
    offset: int = Field(default=0, description="分页偏移量")


class ListContextChainNodesToolOutput(ContextToolResult):
    """查询 Context Chain Node 列表工具输出。"""

    nodes: list[ContextChainNodeQueryResult] = Field(default_factory=list, description="链节点列表")
    total: int = Field(default=0, description="符合条件的总数")
    limit: int = Field(default=0, description="每页条数")
    offset: int = Field(default=0, description="分页偏移量")


class ListContextChainResourcesToolOutput(ContextToolResult):
    """查询 Context Chain Resource 列表工具输出。"""

    resources: list[ContextChainResourceQueryResult] = Field(
        default_factory=list, description="链资源列表"
    )
    total: int = Field(default=0, description="符合条件的总数")
    limit: int = Field(default=0, description="每页条数")
    offset: int = Field(default=0, description="分页偏移量")


class ListContextSelectionRecordsToolOutput(ContextToolResult):
    """查询 Context SelectionRecord 列表工具输出。"""

    selection_records: list[ContextSelectionRecordQueryResult] = Field(
        default_factory=list, description="路由决策记录列表"
    )
    total: int = Field(default=0, description="符合条件的总数")
    limit: int = Field(default=0, description="每页条数")
    offset: int = Field(default=0, description="分页偏移量")
