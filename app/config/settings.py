"""应用全局文件存储、外部服务客户端与处理流水线参数配置模块。"""

from pathlib import Path
from typing import Final

from app.config import environment
from app.modules.document.domain.enums import DocumentStatus

# 1. 项目基础环境与配置加载
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
environment.load_local_env_file(PROJECT_ROOT)

# 2. 文件存储路径与上传限制
BASE_STORAGE_DIR: Final[Path] = Path("storage")
RAW_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "raw"
RAW_LOCAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "local"
RAW_EXTERNAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "external"
SECONDARY_TEXT_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "secondary_text"
CLEANED_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "cleaned"
PROCESSING_STAGING_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "staging"
MAX_UPLOAD_FILE_SIZE: Final[int] = 20 * 1024 * 1024

# 允许上传的文件扩展名与 Content-Type 白名单（注意：白名单仅用于初步校验，不代表文件真实内容格式）。
ALLOWED_EXTENSIONS: Final[set[str]] = {
    ".pdf", ".md", ".markdown", ".csv", ".txt", ".doc", ".docx", ".ppt", ".pptx",
}
ALLOWED_CONTENT_TYPES: Final[set[str]] = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
}

# 3. 文档领域默认值与编号生成规则
DEFAULT_DOCUMENT_STATUS: Final[str] = DocumentStatus.UPLOADED.value
DEFAULT_DOCUMENT_VERSION: Final[int] = 1
DEFAULT_CREATED_BY_ACTOR_CODE: Final[str] = "knowledge_operator_001"
DOCUMENT_CODE_PREFIX: Final[str] = "DOC"
DOCUMENT_CODE_RANDOM_LENGTH: Final[int] = 8

# 4. 数据库与向量存储 (Qdrant) 配置
SQLALCHEMY_DATABASE_URL: Final[str] = environment.get_required_env(
    "SQLALCHEMY_DATABASE_URL"
)
QDRANT_URL: Final[str] = environment.get_env(
    "QDRANT_URL",
    "http://127.0.0.1:6333",
)
QDRANT_COLLECTION_NAME: Final[str] = environment.get_env(
    "QDRANT_COLLECTION_NAME",
    "knowledge_chunks",
)

# 5. 向量嵌入服务 (DashScope / Qwen Embedding)
# 向量维度必须与既有 Qdrant collection 的维度严格一致；修改 EMBEDDING_VECTOR_SIZE 前需重建 collection。
DASHSCOPE_API_KEY: Final[str] = environment.get_required_env("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL: Final[str] = environment.get_env(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
EMBEDDING_MODEL_NAME: Final[str] = environment.get_env(
    "EMBEDDING_MODEL_NAME",
    "text-embedding-v3",
)
EMBEDDING_VECTOR_SIZE: Final[int] = environment.get_int_env(
    "EMBEDDING_VECTOR_SIZE",
    1024,
)
EMBEDDING_BATCH_SIZE: Final[int] = environment.get_int_env(
    "EMBEDDING_BATCH_SIZE",
    10,
)

# 6. 大语言模型服务 (DeepSeek Agent LLM)
DEEPSEEK_API_KEY: Final[str | None] = environment.get_optional_env(
    "DEEPSEEK_API_KEY"
)
DEEPSEEK_BASE_URL: Final[str] = environment.get_env(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com",
)
DEEPSEEK_STRICT_TOOL_BASE_URL: Final[str] = environment.get_env(
    "DEEPSEEK_STRICT_TOOL_BASE_URL",
    "https://api.deepseek.com/beta",
)
DEEPSEEK_MODEL_NAME: Final[str] = environment.get_env(
    "DEEPSEEK_MODEL_NAME",
    "deepseek-v4-flash",
)
DEEPSEEK_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "DEEPSEEK_TIMEOUT_SECONDS",
    60,
)
DEEPSEEK_MAX_RETRIES: Final[int] = environment.get_int_env(
    "DEEPSEEK_MAX_RETRIES",
    2,
)

# 7. Redis 缓存与分布式锁配置 (Context & Runtime)
REDIS_URL: Final[str] = environment.get_env(
    "REDIS_URL",
    "redis://127.0.0.1:6379/0",
)
REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS",
    5,
)
REDIS_SOCKET_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "REDIS_SOCKET_TIMEOUT_SECONDS",
    5,
)
# 同一 Conversation 上下文路由的分布式锁租期（秒）与获取锁的阻塞超时（秒）
CONTEXT_ROUTE_LOCK_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "CONTEXT_ROUTE_LOCK_TIMEOUT_SECONDS",
    240,
)
CONTEXT_ROUTE_LOCK_BLOCKING_TIMEOUT_SECONDS: Final[int] = (
    environment.get_int_env(
        "CONTEXT_ROUTE_LOCK_BLOCKING_TIMEOUT_SECONDS",
        5,
    )
)
CONTEXT_RESOURCE_QUEUE_MAX_SIZE: Final[int] = environment.get_int_env(
    "CONTEXT_RESOURCE_QUEUE_MAX_SIZE",
    16,
)

# 8. 文档转换解析服务 (Docling)
# 复杂办公格式（pdf/doc/docx/ppt/pptx）先由 Docling 转换为 Markdown，之后复用本地 Markdown 清洗切块流水线。
DOCING_SOURCE_TYPES: Final[set[str]] = {"pdf", "doc", "docx", "ppt", "pptx"}
LOCAL_MARKDOWN_SOURCE_TYPES: Final[set[str]] = {"md"}
LOCAL_TEXT_SOURCE_TYPES: Final[set[str]] = {"txt"}
LOCAL_TABLE_SOURCE_TYPES: Final[set[str]] = {"csv"}
DOCLING_SERVER_URL: Final[str] = environment.get_env(
    "DOCLING_SERVER_URL",
    "http://127.0.0.1:5001",
)
DOCLING_CONVERT_ENDPOINT: Final[str] = f"{DOCLING_SERVER_URL}/v1/convert/file"
DOCLING_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "DOCLING_TIMEOUT_SECONDS",
    180,
)
DOCLING_OUTPUT_TYPE: Final[str] = environment.get_env("DOCLING_OUTPUT_TYPE", "md")

# 9. 本地结构化日志与可观测性存储目录 (JSONL)
# 日志存储根目录（相对路径始终按项目根目录解析）
_configured_log_storage_dir = Path(
    environment.get_env("LOG_STORAGE_DIR", "logs")
)
LOG_STORAGE_DIR: Final[Path] = (
    _configured_log_storage_dir
    if _configured_log_storage_dir.is_absolute()
    else PROJECT_ROOT / _configured_log_storage_dir
)
DOCUMENT_LIFECYCLE_LOG_DIR: Final[Path] = (
    LOG_STORAGE_DIR / "document_lifecycle"
)
DOCUMENT_UPLOAD_LOG_DIR: Final[Path] = (
    DOCUMENT_LIFECYCLE_LOG_DIR / "upload"
)
DOCUMENT_PROCESS_LOG_DIR: Final[Path] = (
    DOCUMENT_LIFECYCLE_LOG_DIR / "process"
)
DOCUMENT_CHUNK_LOG_DIR: Final[Path] = (
    DOCUMENT_LIFECYCLE_LOG_DIR / "chunk"
)
DOCUMENT_INDEX_LOG_DIR: Final[Path] = (
    DOCUMENT_LIFECYCLE_LOG_DIR / "index"
)
DOCUMENT_RETRIEVAL_LOG_DIR: Final[Path] = (
    DOCUMENT_LIFECYCLE_LOG_DIR / "retrieval"
)
AGENT_TOOL_LOG_DIR: Final[Path] = LOG_STORAGE_DIR / "agent_tools"
CONTEXT_OBSERVABILITY_LOG_DIR: Final[Path] = LOG_STORAGE_DIR / "context"
