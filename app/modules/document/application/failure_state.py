"""描述文档处理失败登记后的真实状态。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureStateResult:
    """记录条件状态更新是否发生，以及更新前后的实际状态。"""

    state_updated: bool
    status_before: str | None
    status_after: str | None


@dataclass(frozen=True)
class IndexFailureStateResult:
    """分别记录索引失败时 Document 和 ChildChunk 的实际更新。"""

    document_state_updated: bool
    chunk_state_updated_count: int
    status_before: str | None
    status_after: str | None


NO_FAILURE_STATE_CHANGE = FailureStateResult(
    state_updated=False,
    status_before=None,
    status_after=None,
)

NO_INDEX_FAILURE_STATE_CHANGE = IndexFailureStateResult(
    document_state_updated=False,
    chunk_state_updated_count=0,
    status_before=None,
    status_after=None,
)
