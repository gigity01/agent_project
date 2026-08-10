"""Task Runtime 状态枚举。"""

from enum import Enum


class TaskExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPENSATION_REQUIRED = "compensation_required"
    COMPENSATED = "compensated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
