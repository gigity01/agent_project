"""Task Runtime 状态枚举。"""

from enum import Enum


class TaskExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPENSATION_REQUIRED = "compensation_required"
    COMPENSATION_LOCKED = "compensation_locked"
    COMPENSATED = "compensated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CompensationLockReason(str, Enum):
    RETRY_EXHAUSTED = "retry_exhausted"
    SYSTEM_FAILURE = "system_failure"
    UNKNOWN = "unknown"
