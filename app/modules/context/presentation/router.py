"""Context HTTP 路由。"""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.context.application.context_service import ContextService
from app.modules.context.application.dto import (
    ChainTurnUpdate,
    CompleteTurnCommand,
    ContextResourceInput,
    SendMessageCommand,
)
from app.modules.context.application.errors import (
    ContextApplicationError,
    ContextConflictError,
    ContextRoutingError,
    ContextTurnNotFoundError,
    ContextValidationError,
    ConversationLockUnavailable,
)
from app.modules.context.presentation.dependencies import (
    get_context_routing_service,
    get_context_service,
)
from app.modules.context.presentation.schemas import (
    CompleteContextTurnRequest,
    CompleteContextTurnResponse,
    ContextRouteRequest,
    RoutedContextPackage,
)


legacy_router = APIRouter(prefix="/context", tags=["context"])


def _to_http_exception(error: ContextApplicationError) -> HTTPException:
    if isinstance(error, ContextRoutingError):
        status_code = 502
    elif isinstance(error, ContextTurnNotFoundError):
        status_code = 404
    elif isinstance(
        error,
        (ContextConflictError, ConversationLockUnavailable),
    ):
        status_code = 409
    elif isinstance(error, ContextValidationError):
        status_code = 400
    else:
        status_code = 500
    return HTTPException(status_code=status_code, detail=str(error))


def _to_complete_turn_command(
    request: CompleteContextTurnRequest,
) -> CompleteTurnCommand:
    return CompleteTurnCommand(
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


@legacy_router.post(
    "/route",
    response_model=RoutedContextPackage,
    deprecated=True,
)
async def route_context(
    request: ContextRouteRequest,
    service: ContextService = Depends(get_context_routing_service),
) -> RoutedContextPackage:
    """兼容旧 Context Route API；新调用方应发送 Conversation Message。"""
    try:
        result = await service.send_message(
            SendMessageCommand(
                conversation_id=request.conversation_id,
                message=request.user_input,
            )
        )
    except ContextApplicationError as exc:
        raise _to_http_exception(exc) from exc

    return RoutedContextPackage(
        current_turn_id=result.turn_id,
        current_user_input=result.message,
        selected_chains=result.selected_chains,
        new_chain_id=result.new_chain_id,
        route_decision=result.decision,
    )


@legacy_router.post(
    "/turns/{turn_id}/complete",
    response_model=CompleteContextTurnResponse,
)
async def complete_context_turn(
    turn_id: str,
    request: CompleteContextTurnRequest,
    service: ContextService = Depends(get_context_service),
) -> CompleteContextTurnResponse:
    """完成已保存路由决定的 Context Turn。"""
    try:
        result = await service.complete_turn(
            turn_id,
            _to_complete_turn_command(request),
        )
    except ContextApplicationError as exc:
        raise _to_http_exception(exc) from exc

    return CompleteContextTurnResponse(
        turn=result.turn,
        linked_chain_ids=result.linked_chain_ids,
    )
