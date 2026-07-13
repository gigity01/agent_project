"""文档处理生命周期状态。"""

from enum import Enum


class DocumentStatus(str, Enum):
    """表示上传、处理、切块和索引流程中的文档阶段。"""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    EXPIRED = "expired"
