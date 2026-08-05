"""Conversation Message 命令与外部稳定结果。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.context.domain.enums import ContextRouteMode


class SendConversationMessageCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)


class RoutingMetadata(BaseModel):
    route_mode: ContextRouteMode
    selected_chain_ids: list[str]
    new_chain_id: str | None
    reason_summary: str


class SendConversationMessageResult(BaseModel):
    conversation_id: str
    turn_id: str
    plan_id: str | None
    status: Literal[
        "processing",
        "unsupported",
        "needs_clarification",
        "retry_pending",
        "completed",
        "failed",
    ]
    assistant_message: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    routing: RoutingMetadata | None = None


class TurnStatusResult(BaseModel):
    conversation_id: str
    turn_id: str
    turn_status: str
    plan_id: str | None
    plan_status: str | None
    revision: int | None
    task_ids: list[str]
    assistant_message: str | None
