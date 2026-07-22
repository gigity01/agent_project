"""描述生命周期失败登记后的真实文档状态。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureStateResult:
    """记录条件状态更新是否发生，以及更新前后的实际状态。"""

    state_updated: bool
    status_before: str | None
    status_after: str | None


NO_FAILURE_STATE_CHANGE = FailureStateResult(
    state_updated=False,
    status_before=None,
    status_after=None,
)
