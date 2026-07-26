"""Context Chain 资源历史事件动作。"""

from enum import Enum


class ContextResourceAction(str, Enum):
    """资源被首次引用、再次使用或明确移除。"""

    SEEN = "seen"
    REFRESHED = "refreshed"
    REMOVED = "removed"
    INVALIDATED = "invalidated"
