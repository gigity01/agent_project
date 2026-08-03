"""Context 只读 Function Tool Schema。"""

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.context.application.query_dto import (
    ContextChainNodeQueryResult,
    ContextChainNodeSearchQuery,
    ContextChainQueryResult,
    ContextChainResourceQueryResult,
    ContextChainResourceSearchQuery,
    ContextChainSearchQuery,
    ContextRouteRecordQueryResult,
    ContextRouteRecordSearchQuery,
    ConversationTurnQueryResult,
    ConversationTurnSearchQuery,
)


class GetConversationTurnToolInput(BaseModel):
    turn_id: str = Field(min_length=1, max_length=100)


class ListConversationTurnsToolInput(ConversationTurnSearchQuery):
    """Conversation Turn 查询输入。"""


class GetContextChainToolInput(BaseModel):
    chain_id: str = Field(min_length=1, max_length=100)


class ListContextChainsToolInput(ContextChainSearchQuery):
    """Context Chain 查询输入。"""


class ListContextChainNodesToolInput(ContextChainNodeSearchQuery):
    """Context Chain Node 查询输入。"""


class ListContextChainResourcesToolInput(ContextChainResourceSearchQuery):
    """Context Chain Resource 查询输入。"""


class ListContextRouteRecordsToolInput(ContextRouteRecordSearchQuery):
    """Context RouteRecord 查询输入。"""


class ContextToolResult(BaseModel):
    outcome: Literal["succeeded", "rejected", "failed"]
    result_code: str
    message: str
    retryable: bool
    resource_refs: list[str]


class GetConversationTurnToolOutput(ContextToolResult):
    turn: ConversationTurnQueryResult | None = None


class ListConversationTurnsToolOutput(ContextToolResult):
    turns: list[ConversationTurnQueryResult] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class GetContextChainToolOutput(ContextToolResult):
    chain: ContextChainQueryResult | None = None


class ListContextChainsToolOutput(ContextToolResult):
    chains: list[ContextChainQueryResult] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class ListContextChainNodesToolOutput(ContextToolResult):
    nodes: list[ContextChainNodeQueryResult] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class ListContextChainResourcesToolOutput(ContextToolResult):
    resources: list[ContextChainResourceQueryResult] = Field(
        default_factory=list
    )
    total: int = 0
    limit: int = 0
    offset: int = 0


class ListContextRouteRecordsToolOutput(ContextToolResult):
    route_records: list[ContextRouteRecordQueryResult] = Field(
        default_factory=list
    )
    total: int = 0
    limit: int = 0
    offset: int = 0
