"""Conversation 用户消息 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.dependencies import (
    get_context_routing_service,
)
from app.schemas.context import (
    ContextRouteRequest,
    RoutedContextPackage,
    SendConversationMessageRequest,
)
from app.services.context_service import ContextService


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
    return await service.route_context(
        ContextRouteRequest(
            conversation_id=conversation_id,
            user_input=request.message,
        )
    )
