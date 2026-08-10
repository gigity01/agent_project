"""应用的文件存储、外部服务与处理参数配置。"""

from pathlib import Path
from typing import Final

from app.config import environment
from app.modules.document.domain.enums import DocumentStatus


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
environment.load_local_env_file(PROJECT_ROOT)

# 文件上传与派生产物存储。路径保留为相对路径，由调用服务在项目根目录启动
# 时解析；原始文件与外部转换得到的中间文本分目录存放，便于失败补偿和追溯。
BASE_STORAGE_DIR: Final[Path] = Path("storage")
RAW_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "raw"
RAW_LOCAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "local"
RAW_EXTERNAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "external"
SECONDARY_TEXT_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "secondary_text"
CLEANED_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "cleaned"
PROCESSING_STAGING_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "staging"
MAX_UPLOAD_FILE_SIZE: Final[int] = 20 * 1024 * 1024

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

# 文档默认值与编号规则。
DEFAULT_DOCUMENT_STATUS: Final[str] = DocumentStatus.UPLOADED.value
DEFAULT_DOCUMENT_VERSION: Final[int] = 1
DEFAULT_CREATED_BY_ACTOR_CODE: Final[str] = "knowledge_operator_001"
DOCUMENT_CODE_PREFIX: Final[str] = "DOC"
DOCUMENT_CODE_RANDOM_LENGTH: Final[int] = 8

# 数据库与检索服务。连接地址可由部署环境覆盖，默认值仅适用于本地开发。
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

# DashScope / Qwen Embedding。向量维度必须与既有 Qdrant collection 一致，
# 修改 EMBEDDING_VECTOR_SIZE 前需要重建或迁移 collection。
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

# DeepSeek Agent LLM。该配置与 DashScope Embedding 相互独立。
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

# Context Redis。应用生命周期持有一个异步客户端，路由锁和热资源队列共享连接池。
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

# 文档转换服务。复杂办公文件先转换为 Markdown，之后复用本地 Markdown
# 处理器，避免各格式分别维护清洗和切块逻辑。
DOCING_SOURCE_TYPES: Final[set[str]] = {"pdf", "doc", "docx", "ppt", "pptx"}
LOCAL_MARKDOWN_SOURCE_TYPES: Final[set[str]] = {"md"}
LOCAL_TEXT_SOURCE_TYPES: Final[set[str]] = {"txt"}
LOCAL_TABLE_SOURCE_TYPES: Final[set[str]] = {"csv"}
DOCLING_SERVER_URL: Final[str] = environment.get_env(
    "DOCLING_SERVER_URL",
    "http://115.29.238.225:5001",
)
DOCLING_CONVERT_ENDPOINT: Final[str] = f"{DOCLING_SERVER_URL}/v1/convert/file"
DOCLING_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "DOCLING_TIMEOUT_SECONDS",
    180,
)
DOCLING_OUTPUT_TYPE: Final[str] = environment.get_env("DOCLING_OUTPUT_TYPE", "md")

# 本地结构化日志目录。相对路径始终按项目根目录解析。
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
