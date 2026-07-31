"""Conversation 用户消息 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.agents.context_agent import ContextAgentRouter
from app.api.dependencies import (
    get_context_agent_router,
    get_context_resource_service,
    get_context_route_lock_manager,
)
from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
)
from app.schemas.context import (
    ContextRouteRequest,
    RoutedContextPackage,
    SendConversationMessageRequest,
)
from app.services.context_resource_service import ContextResourceService
from app.services.context_service import ContextService


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


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
    agent_router: ContextAgentRouter = Depends(
        get_context_agent_router
    ),
    route_lock_manager: ConversationRouteLockManager = Depends(
        get_context_route_lock_manager
    ),
    resource_service: ContextResourceService = Depends(
        get_context_resource_service
    ),
) -> RoutedContextPackage:
    """接收用户消息，并交由后端 Context Service 完成上下文路由。"""
    service = ContextService(
        agent_router=agent_router,
        route_lock_manager=route_lock_manager,
        resource_service=resource_service,
    )
    return await service.route_context(
        ContextRouteRequest(
            conversation_id=conversation_id,
            user_input=request.message,
        )
    )
