"""文档模块的领域状态与产物类型枚举定义。

定义文档流水线三状态轴（处理阶段状态、业务生命周期状态、底层存储状态）
以及派生产物（Artifact）的角色、类型和有效性状态。
"""

from enum import Enum


class DocumentArtifactRole(str, Enum):
    """区分文档派生产物在流水线中扮演的角色。

    Attributes:
        PROCESS_INPUT: 格式转换/清洗阶段的直接输入文件（如经外部转换得到的 Markdown 中间件）。
        PROCESS_OUTPUT: 清洗与转换步骤产生的标准输出文本。
        CHUNK_INPUT: 传递给切块器（Chunker）的清洗后文本。
        DEBUG_ARTIFACT: 辅助排错与审计的调试产物（如布局信息 JSON、中间日志等）。
    """

    PROCESS_INPUT = "process_input"
    PROCESS_OUTPUT = "process_output"
    CHUNK_INPUT = "chunk_input"
    DEBUG_ARTIFACT = "debug_artifact"


class DocumentArtifactStatus(str, Enum):
    """标记派生产物当前所处的生命周期与有效性状态。

    Attributes:
        CREATED: 产物记录已创建，但尚未完成写入或校验。
        ACTIVE: 产物当前有效且处于激活状态，作为下游处理的唯一正式输入/输出依据。
        SUPERSEDED: 已被同一用途的最新产物替换/废弃。
        FAILED: 产物生成或写入过程中发生不可恢复的错误。
    """

    CREATED = "created"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class DocumentArtifactType(str, Enum):
    """区分产物的具体内容类型与媒介格式。

    Attributes:
        SECONDARY_TEXT: 复杂办公格式（PDF/Word/PPT）经 Docling 等外部工具提取的二级文本（Markdown）。
        CLEANED_TEXT: 经过规则清洗、空行规范化与非法字符过滤后的标准正文。
        LAYOUT_JSON: 文档解析器生成的版面结构、段落与坐标元数据。
        EXTRACTED_TABLE: 从原文档中抽取出的表格结构化数据。
        EXTRACTED_IMAGE: 从原文档中抽取出的图片或图表资源。
    """

    SECONDARY_TEXT = "secondary_text"
    CLEANED_TEXT = "cleaned_text"
    LAYOUT_JSON = "layout_json"
    EXTRACTED_TABLE = "extracted_table"
    EXTRACTED_IMAGE = "extracted_image"


class DocumentLifecycleStatus(str, Enum):
    """表示文档在业务层面的有效性状态。

    与技术流水线处理阶段（DocumentStatus）解耦，专注于业务可见性与过期策略。

    Attributes:
        SCHEDULED: 计划生效状态（未到生效日期）。
        ACTIVE: 业务上正常有效、可供检索与引用的文档。
        EXPIRED: 业务有效期届满，已自动或手动失效。
        REPLACED: 已被更新版本的同名或替代文档替换。
        DELETED: 已在业务层面软删除或标记废弃。
    """

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    EXPIRED = "expired"
    REPLACED = "replaced"
    DELETED = "deleted"


class DocumentStatus(str, Enum):
    """表示文档在四阶段处理流水线中的当前技术阶段状态。

    状态流转路径：
    uploaded -> processing -> processed -> chunking -> chunked -> indexing -> indexed
                             \\_______________________________________________
                                              任一阶段失败 -> failed

    Attributes:
        UPLOADED: 原件已上传并校验通过，元数据与原始文件已落盘。
        PROCESSING: 正在执行格式转换（如 Docling）或文本清洗。
        PROCESSED: 格式转换与清洗已成功完成，已产出 active 状态的 cleaned 文本产物。
        CHUNKING: 正在构建父级语义块与子切块。
        CHUNKED: 父级语义块与子切块已完成持久化，待生成向量索引。
        INDEXING: 正在调用 Embedding 服务并向 Qdrant 写入向量。
        INDEXED: 向量已全部写入 Qdrant 且数据库状态已同步，文档可供知识库检索。
        FAILED: 某一流水线阶段发生不可恢复的错误，等待补偿、修复或重试。
    """

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class DocumentStorageStatus(str, Enum):
    """表示文档原始文件与产物文件在存储介质中的归档状态。

    Attributes:
        ACTIVE: 文件位于本地热存储区，可随时读取与处理。
        ARCHIVING: 正在向冷存储或归档介质传输与迁移。
        ARCHIVED: 文件已成功归档到冷存储，本地热存储可能已清理。
        ARCHIVE_FAILED: 归档迁移过程失败。
    """

    ACTIVE = "active"
    ARCHIVING = "archiving"
    ARCHIVED = "archived"
    ARCHIVE_FAILED = "archive_failed"
