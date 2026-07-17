"""文档业务生命周期状态。"""

from enum import Enum


class DocumentLifecycleStatus(str, Enum):
    """表示文档在业务上是否可用以及失效原因。"""

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    EXPIRED = "expired"
    REPLACED = "replaced"
    DELETED = "deleted"
