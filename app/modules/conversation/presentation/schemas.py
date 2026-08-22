"""Conversation HTTP Schema。"""

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.conversation.application.dto import ContextSelectionMetadata


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    source_turn_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class SendMessageResponse(BaseModel):
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


class TurnStatusResponse(BaseModel):
    conversation_id: str
    turn_id: str
    turn_status: str
    plan_id: str | None
    plan_status: str | None
    revision: int | None
    task_ids: list[str]
    assistant_message: str | None
