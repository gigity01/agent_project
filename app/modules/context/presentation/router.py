"""Context HTTP 路由定义。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.modules.context.application.context_service import ContextService
from app.modules.context.application.dto import (
    ChainTurnUpdate,
    CompleteTurnCommand,
    ContextResourceInput,
    SendMessageCommand,
    TurnAttribution,
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
    ContextSelectionRequest,
    SelectedContextPackage,
)


legacy_router = APIRouter(prefix="/context", tags=["context"])


def _to_http_exception(error: ContextApplicationError) -> HTTPException:
    """将 Context 应用层业务异常安全映射为 HTTP 协议状态码。

    映射规则：
    - ContextRoutingError -> 502 Bad Gateway
    - ContextTurnNotFoundError -> 404 Not Found
    - ContextConflictError / ConversationLockUnavailable -> 409 Conflict
    - ContextValidationError -> 400 Bad Request
    - 其他 ContextApplicationError -> 500 Internal Server Error

    Args:
        error: ContextApplicationError 实例。

    Returns:
        HTTPException: FastAPI HTTP 异常对象。
    """
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
    """将 CompleteContextTurnRequest 请求 Schema 转换为 CompleteTurnCommand 应用层命令 DTO。

    Args:
        request: CompleteContextTurnRequest 实例。

    Returns:
        CompleteTurnCommand: 转换后的应用层命令对象。
    """
    return CompleteTurnCommand(
        assistant_content=request.assistant_content,
        assistant_compact=request.assistant_compact,
        task_ids=list(request.task_ids),
        task_result_summary=request.task_result_summary,
        attribution=TurnAttribution(
            existing_chain_ids=list(
                request.attribution.existing_chain_ids
            ),
            create_new_chain=request.attribution.create_new_chain,
            new_chain_id=request.attribution.new_chain_id,
        ),
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
    response_model=SelectedContextPackage,
    deprecated=True,
)
async def select_context(
    request: ContextSelectionRequest,
    service: ContextService = Depends(get_context_routing_service),
) -> SelectedContextPackage:
    """执行历史 Context Selection 路由判定（已废弃的兼容端点）。

    注意：此接口仅供向后兼容，不决定当前 Turn 的最终链归属。

    Args:
        request: ContextSelectionRequest 请求体。
        service: 注入的 ContextService 实例。

    Returns:
        SelectedContextPackage: 包含命中的上下文链与选择决策。

    Raises:
        HTTPException: 当底层发生路由失败、锁超时或参数校验错误时抛出对应状态码。
    """
    try:
        result = await service.send_message(
            SendMessageCommand(
                conversation_id=request.conversation_id,
                message=request.user_input,
            )
        )
    except ContextApplicationError as exc:
        raise _to_http_exception(exc) from exc

    return SelectedContextPackage(
        current_turn_id=result.turn_id,
        current_user_input=result.message,
        context_chains=result.context_chains,
        selection_decision=result.decision,
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
    """下游完成处理后补全唯一 Turn 并建立链节点与资源关联。

    Args:
        turn_id: 待完成的 Turn 标识。
        request: CompleteContextTurnRequest 请求体。
        service: 注入的 ContextService 实例。

    Returns:
        CompleteContextTurnResponse: 包含完成后的 Turn 与关联链 ID 列表。

    Raises:
        HTTPException: 当 Turn 不存在、状态冲突或更新不合法时抛出对应状态码。
    """
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
