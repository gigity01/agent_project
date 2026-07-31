"""Context 子系统内部 API。"""

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_context_routing_service,
    get_context_service,
)
from app.api.context_error_mapping import to_context_http_exception
from app.modules.context.application.context_service import ContextService
from app.modules.context.application.dto import (
    ChainTurnUpdate,
    CompleteTurnCommand,
    ContextResourceInput,
    SendMessageCommand,
)
from app.modules.context.application.errors import ContextApplicationError
from app.schemas.context import (
    CompleteContextTurnRequest,
    CompleteContextTurnResponse,
    ContextRouteRequest,
    RoutedContextPackage,
)


router = APIRouter(prefix="/context", tags=["context"])


@router.post(
    "/route",
    response_model=RoutedContextPackage,
)
async def route_context(
    request: ContextRouteRequest,
    service: ContextService = Depends(get_context_routing_service),
) -> RoutedContextPackage:
    try:
        result = await service.send_message(
            SendMessageCommand(
                conversation_id=request.conversation_id,
                message=request.user_input,
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


@router.post(
    "/turns/{turn_id}/complete",
    response_model=CompleteContextTurnResponse,
)
async def complete_context_turn(
    turn_id: str,
    request: CompleteContextTurnRequest,
    service: ContextService = Depends(get_context_service),
) -> CompleteContextTurnResponse:
    command = CompleteTurnCommand(
        assistant_content=request.assistant_content,
        assistant_compact=request.assistant_compact,
        task_ids=list(request.task_ids),
        task_result_summary=request.task_result_summary,
        chain_updates=[
            ChainTurnUpdate(
                chain_id=update.chain_id,
                related_task_ids=list(update.related_task_ids),
                related_resources=[
                    ContextResourceInput(
                        resource_type=resource.resource_type,
                        resource_id=resource.resource_id,
                        relation=resource.relation,
                        summary=resource.summary,
                    )
                    for resource in update.related_resources
                ],
                removed_resource_keys=list(
                    update.removed_resource_keys
                ),
            )
            for update in request.chain_updates
        ],
    )
    try:
        result = await service.complete_turn(turn_id, command)
    except ContextApplicationError as exc:
        raise to_context_http_exception(exc) from exc
    return CompleteContextTurnResponse(
        turn=result.turn,
        linked_chain_ids=result.linked_chain_ids,
    )
