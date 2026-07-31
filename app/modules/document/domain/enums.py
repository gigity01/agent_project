"""文档模块的业务状态枚举。"""

from enum import Enum


class DocumentArtifactRole(str, Enum):
    """区分处理输入、输出、切块输入与调试产物。"""

    PROCESS_INPUT = "process_input"
    PROCESS_OUTPUT = "process_output"
    CHUNK_INPUT = "chunk_input"
    DEBUG_ARTIFACT = "debug_artifact"


class DocumentArtifactStatus(str, Enum):
    """标记派生产物是否当前有效、被替代或处理失败。"""

    CREATED = "created"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class DocumentArtifactType(str, Enum):
    """区分二级文本、清洗文本、布局与多媒体提取产物。"""

    SECONDARY_TEXT = "secondary_text"
    CLEANED_TEXT = "cleaned_text"
    LAYOUT_JSON = "layout_json"
    EXTRACTED_TABLE = "extracted_table"
    EXTRACTED_IMAGE = "extracted_image"


class DocumentLifecycleStatus(str, Enum):
    """表示文档在业务上是否可用以及失效原因。"""

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    EXPIRED = "expired"
    REPLACED = "replaced"
    DELETED = "deleted"


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


class DocumentStorageStatus(str, Enum):
    """表示文档文件位于活跃区还是处于归档流程。"""

    ACTIVE = "active"
    ARCHIVING = "archiving"
    ARCHIVED = "archived"
    ARCHIVE_FAILED = "archive_failed"
