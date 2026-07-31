"""Context HTTP 请求与响应模型。"""

from pydantic import BaseModel, Field

from app.modules.context.domain.enums import ContextRouteMode
from app.modules.context.domain.models import (
    ContextChain,
    ContextRouteDecision,
    ConversationTurn,
)


class SendMessageRequest(BaseModel):
    """用户发送 Conversation Message 的请求。"""

    message: str = Field(min_length=1)


class ContextRoutingMetadata(BaseModel):
    """联调阶段向调用方返回的精简路由元数据。"""

    route_mode: ContextRouteMode
    selected_chain_ids: list[str]
    new_chain_id: str | None
    reason_summary: str


class SendMessageResponse(BaseModel):
    """Conversation Message 完成路由后的外部响应。"""

    conversation_id: str
    turn_id: str
    status: str
    routing: ContextRoutingMetadata


class ContextRouteRequest(BaseModel):
    """旧 Context Route 兼容请求。"""

    conversation_id: str = Field(min_length=1, max_length=100)
    user_input: str = Field(min_length=1)


class RoutedContextPackage(BaseModel):
    """旧 Context Route 兼容响应。"""

    current_turn_id: str
    current_user_input: str
    selected_chains: list[ContextChain]
    new_chain_id: str | None = None
    route_decision: ContextRouteDecision


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


SendConversationMessageRequest = SendMessageRequest
