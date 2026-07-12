"""文档派生产物的生命周期状态枚举。"""

from enum import Enum
class DocumentArtifactStatus(str, Enum):
    """标记派生产物是否当前有效、被替代或处理失败。"""
    CREATED = "created"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"
