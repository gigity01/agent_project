"""Context 子系统内部 API。"""

from fastapi import APIRouter, Depends

from app.agents.context_agent import ContextAgentRouter
from app.api.dependencies import (
    get_context_agent_router,
    get_context_route_lock_manager,
)
from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
)
from app.schemas.context import (
    CompleteContextTurnRequest,
    CompleteContextTurnResponse,
    ContextRouteRequest,
    RoutedContextPackage,
)
from app.services.context_service import ContextService


router = APIRouter(prefix="/api/context", tags=["context"])


@router.post(
    "/route",
    response_model=RoutedContextPackage,
)
async def route_context(
    request: ContextRouteRequest,
    agent_router: ContextAgentRouter = Depends(
        get_context_agent_router
    ),
    route_lock_manager: ConversationRouteLockManager = Depends(
        get_context_route_lock_manager
    ),
) -> RoutedContextPackage:
    service = ContextService(
        agent_router=agent_router,
        route_lock_manager=route_lock_manager,
    )
    return await service.route_context(request)


@router.post(
    "/turns/{turn_id}/complete",
    response_model=CompleteContextTurnResponse,
)
async def complete_context_turn(
    turn_id: str,
    request: CompleteContextTurnRequest,
    route_lock_manager: ConversationRouteLockManager = Depends(
        get_context_route_lock_manager
    ),
) -> CompleteContextTurnResponse:
    service = ContextService(
        agent_router=None,
        route_lock_manager=route_lock_manager,
    )
    return await service.complete_turn(turn_id, request)
