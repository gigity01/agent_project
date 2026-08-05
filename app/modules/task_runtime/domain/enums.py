"""Task Runtime 状态枚举。"""

from enum import Enum


class TaskExecutionStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
