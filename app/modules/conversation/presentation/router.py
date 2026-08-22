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
    try:
        return TurnStatusResponse.model_validate(
            use_case.execute(conversation_id, turn_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
