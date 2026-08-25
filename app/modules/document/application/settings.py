"""Document 业务用例所需的不可变运行配置参数。

定义上传、清洗转换与向量索引阶段的参数对象，由应用配置层提供初始化并注入。
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentUploadSettings:
    """文档上传用例（UploadDocumentUseCase）配置参数。

    Attributes:
        raw_local_storage_dir: 本地源格式（txt, md, csv）原始文件存储目录。
        raw_external_storage_dir: 需外部转换格式（pdf, docx, pptx 等）原始文件存储目录。
        max_upload_file_size: 最大允许上传文件字节数（默认 20 MiB）。
        default_document_status: 文档新建时的初始技术状态（默认 'uploaded'）。
        default_document_version: 初始版本号（默认 1）。
        default_created_by_actor_code: 默认创建人编码。
        document_code_prefix: 文档业务编码（doc_code）前缀。
        document_code_random_length: 业务编码中随机字符串长度。
    """

    raw_local_storage_dir: Path
    raw_external_storage_dir: Path
    max_upload_file_size: int
    default_document_status: str
    default_document_version: int
    default_created_by_actor_code: str
    document_code_prefix: str
    document_code_random_length: int


@dataclass(frozen=True)
class DocumentProcessingSettings:
    """文档处理用例（ProcessDocumentUseCase）配置参数。

    Attributes:
        cleaned_storage_dir: 正式清洗文本产物持久化目录。
        secondary_text_storage_dir: Docling 等提取的二级文本（Markdown）存储目录。
        staging_storage_dir: 操作级临时文件 staging 暂存根目录（以 operation_id 隔离）。
    """

    cleaned_storage_dir: Path
    secondary_text_storage_dir: Path
    staging_storage_dir: Path


@dataclass(frozen=True)
class DocumentIndexingSettings:
    """文档向量索引发布与用例（IndexVectorsUseCase）配置参数。

    Attributes:
        embedding_batch_size: 批量调用 Embedding API 的子块批次大小（如 16 或 32）。
        embedding_model_name: 使用的向量模型名称（如 'text-embedding-v3' / 'qwen-embedding'）。
        embedding_vector_size: 期望的向量维度大小（如 1536 或 1024），用于校验模型输出。
    """

    embedding_batch_size: int
    embedding_model_name: str
    embedding_vector_size: int
