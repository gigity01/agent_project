"""文档失败状态 DTO 的兼容导出。"""

from app.modules.document.application.failure_state import (
    FailureStateResult,
    IndexFailureStateResult,
    NO_FAILURE_STATE_CHANGE,
    NO_INDEX_FAILURE_STATE_CHANGE,
)

__all__ = [
    "FailureStateResult",
    "IndexFailureStateResult",
    "NO_FAILURE_STATE_CHANGE",
    "NO_INDEX_FAILURE_STATE_CHANGE",
]
