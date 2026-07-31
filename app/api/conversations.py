"""Conversation 用户消息 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.dependencies import (
    get_context_routing_service,
)
from app.api.context_error_mapping import to_context_http_exception
from app.modules.context.application.context_service import ContextService
from app.modules.context.application.dto import SendMessageCommand
from app.modules.context.application.errors import ContextApplicationError
from app.schemas.context import (
    RoutedContextPackage,
    SendConversationMessageRequest,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "/{conversation_id}/messages",
    response_model=RoutedContextPackage,
)
async def send_conversation_message(
    conversation_id: Annotated[
        str,
        Path(min_length=1, max_length=100),
    ],
    request: SendConversationMessageRequest,
    service: ContextService = Depends(get_context_routing_service),
) -> RoutedContextPackage:
    """接收用户消息，并交由后端 Context Service 完成上下文路由。"""
    try:
        result = await service.send_message(
            SendMessageCommand(
                conversation_id=conversation_id,
                message=request.message,
            )
        )
    except ContextApplicationError as exc:
        raise to_context_http_exception(exc) from exc
    return RoutedContextPackage(
        current_turn_id=result.turn_id,
        current_user_input=result.message,
        selected_chains=result.selected_chains,
        new_chain_id=result.new_chain_id,
        route_decision=result.decision,
    )
