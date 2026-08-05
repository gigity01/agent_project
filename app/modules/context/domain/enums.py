"""Context 领域枚举。"""

from enum import Enum


class ContextRouteMode(str, Enum):
    """Context Agent 支持的固定路由模式。"""

    SINGLE_MATCH = "single_match"
    MULTI_MATCH = "multi_match"
    NEW_CHAIN = "new_chain"
    EXISTING_AND_NEW = "existing_and_new"
    FALLBACK_LATEST = "fallback_latest"


class ContextTurnStatus(str, Enum):
    """Turn 从创建、完成路由到下游处理完成的状态。"""

    ROUTING = "routing"
    ROUTED = "routed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ContextResourceAction(str, Enum):
    """资源被首次引用、再次使用或明确移除。"""

    SEEN = "seen"
    REFRESHED = "refreshed"
    REMOVED = "removed"
    INVALIDATED = "invalidated"
