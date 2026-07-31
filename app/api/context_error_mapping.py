"""Context Application 异常到 HTTP 响应的兼容映射。"""

from fastapi import HTTPException

from app.modules.context.application.errors import (
    ContextApplicationError,
    ContextConflictError,
    ContextRoutingError,
    ContextTurnNotFoundError,
    ContextValidationError,
    ConversationLockUnavailable,
)


def to_context_http_exception(
    error: ContextApplicationError,
) -> HTTPException:
    """保持 Context API 既有 HTTP 状态与错误文本。"""
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
