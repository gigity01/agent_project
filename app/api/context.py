"""Context 子系统内部 API。"""

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_context_routing_service,
    get_context_service,
)
from app.schemas.context import (
    CompleteContextTurnRequest,
    CompleteContextTurnResponse,
    ContextRouteRequest,
    RoutedContextPackage,
)
from app.services.context_service import ContextService


router = APIRouter(prefix="/context", tags=["context"])


@router.post(
    "/route",
    response_model=RoutedContextPackage,
)
async def route_context(
    request: ContextRouteRequest,
    service: ContextService = Depends(get_context_routing_service),
) -> RoutedContextPackage:
    return await service.route_context(request)


@router.post(
    "/turns/{turn_id}/complete",
    response_model=CompleteContextTurnResponse,
)
async def complete_context_turn(
    turn_id: str,
    request: CompleteContextTurnRequest,
    service: ContextService = Depends(get_context_service),
) -> CompleteContextTurnResponse:
    return await service.complete_turn(turn_id, request)
