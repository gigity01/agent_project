"""Conversation Message 命令与外部稳定结果。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.context.domain.enums import ContextSelectionMode


class SendConversationMessageCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)
    source_turn_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class ContextSelectionMetadata(BaseModel):
    selection_mode: ContextSelectionMode
    relevant_chain_ids: list[str]
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
    context_selection: ContextSelectionMetadata | None = None


class TurnStatusResult(BaseModel):
    conversation_id: str
    turn_id: str
    turn_status: str
    plan_id: str | None
    plan_status: str | None
    revision: int | None
    task_ids: list[str]
    assistant_message: str | None
