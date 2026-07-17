"""文档文件存储状态。"""

from enum import Enum


class DocumentStorageStatus(str, Enum):
    """表示文档文件位于活跃区还是处于归档流程。"""

    ACTIVE = "active"
    ARCHIVING = "archiving"
    ARCHIVED = "archived"
    ARCHIVE_FAILED = "archive_failed"
