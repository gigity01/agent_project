"""Conversation Turn 在 Context 子系统中的处理状态。"""

from enum import Enum


class ContextTurnStatus(str, Enum):
    """Turn 从创建、完成路由到下游处理完成的状态。"""

    ROUTING = "routing"
    ROUTED = "routed"
    COMPLETED = "completed"
    FAILED = "failed"
