"""正式 Conversation Message HTTP 路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from app.modules.clarification.application.errors import (
    ClarificationApplicationError,
)
from app.modules.context.application.errors import (
    ContextApplicationError,
    ContextConflictError,
    ContextRoutingError,
    ContextTurnNotFoundError,
    ContextValidationError,
    ConversationLockUnavailable,
)
from app.modules.conversation.application.dto import (
    SendConversationMessageCommand,
)
from app.modules.conversation.presentation.dependencies import (
    get_send_conversation_message,
    get_turn_status,
)
from app.modules.conversation.presentation.schemas import (
    SendMessageRequest,
    SendMessageResponse,
    TurnStatusResponse,
)
from app.modules.planning.application.errors import PlanningApplicationError


router = APIRouter(prefix="/conversations", tags=["conversations"])


def _context_status_code(exc: ContextApplicationError) -> int:
    if isinstance(exc, ContextRoutingError):
        return 502
    if isinstance(exc, ContextTurnNotFoundError):
        return 404
    if isinstance(exc, (ContextConflictError, ConversationLockUnavailable)):
        return 409
    if isinstance(exc, ContextValidationError):
        return 400
    return 500


@router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_conversation_message(
    conversation_id: Annotated[str, Path(min_length=1, max_length=100)],
    request: SendMessageRequest,
    response: Response,
    use_case=Depends(get_send_conversation_message),
) -> SendMessageResponse:
    """接收用户消息或针对澄清提问的回复，执行上下文路由与规划。

    响应状态码规则：
    - HTTP 202 Accepted: 规划成功并已发布异步 Plan（status 为 processing 或 retry_pending），客户端需通过 Turn 查询接口轮询结果。
    - HTTP 200 OK: 即时返回非异步终态（needs_clarification、unsupported 或 failed）。
    - HTTP 400/404/409/502: 对应的参数校验、资源不存在、并发锁冲突或外部路由失败异常。
    """
    try:
        result = await use_case.execute(
            SendConversationMessageCommand(
                conversation_id=conversation_id,
                message=request.message,
                source_turn_id=request.source_turn_id,
            )
        )
    except ContextApplicationError as exc:
        raise HTTPException(
            status_code=_context_status_code(exc),
            detail=str(exc),
        ) from exc
    except PlanningApplicationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ClarificationApplicationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if result.status in {"processing", "retry_pending"}:
        response.status_code = 202
    return SendMessageResponse.model_validate(result.model_dump())


@router.get(
    "/{conversation_id}/turns/{turn_id}",
    response_model=TurnStatusResponse,
)
def get_conversation_turn_status(
    conversation_id: Annotated[str, Path(min_length=1, max_length=100)],
    turn_id: Annotated[str, Path(min_length=1, max_length=100)],
    use_case=Depends(get_turn_status),
) -> TurnStatusResponse:
    """查询指定 Turn 的当前状态、关联的最新 Plan Revision 及任务执行结果。"""
    try:
        return TurnStatusResponse.model_validate(
            use_case.execute(conversation_id, turn_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
