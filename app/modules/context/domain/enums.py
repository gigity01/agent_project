"""Context 领域枚举。"""

from enum import Enum


class ContextSelectionMode(str, Enum):
    """Planner 历史上下文读取集合的派生规模。"""

    NO_CONTEXT = "no_context"
    SINGLE_CONTEXT = "single_context"
    MULTI_CONTEXT = "multi_context"


class ContextTurnStatus(str, Enum):
    """Turn 从构建历史读取集合到下游处理完成的状态。"""

    ROUTING = "routing"
    CONTEXT_READY = "context_ready"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ContextResourceAction(str, Enum):
    """资源被首次引用、再次使用或明确移除。"""

    SEEN = "seen"
    REFRESHED = "refreshed"
    REMOVED = "removed"
    INVALIDATED = "invalidated"
