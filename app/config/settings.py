"""应用全局文件存储、外部服务客户端与处理流水线参数配置模块。

职责说明：
- 声明并导出系统各模块运行所需的全部静态常量与环境变量配置项。
- 涵盖配置分组：
  1. 项目根路径与 `.env` 环境变量加载；
  2. 原始文件、Docling 中间文本、清洗文本与 Staging 暂存目录配置及上传约束；
  3. 文档生命周期默认值与编号生成规则；
  4. MySQL 关系数据库与 Qdrant 向量数据库连接配置；
  5. DashScope (Qwen) Embedding 向量模型与批处理参数；
  6. DeepSeek LLM 提供者参数（API Key、Base URL、超时与重试）；
  7. Redis 连接、超时、Conversation 路由锁租期与热资源队列容量；
  8. Docling 复杂格式解析服务地址与转换超时；
  9. 可观测性 JSONL 结构化日志目录路径定义。
"""

from pathlib import Path
from typing import Final

from app.config import environment
from app.modules.document.domain.enums import DocumentStatus


# ----------------------------------------------------------------------
# 1. 项目基础环境与配置加载
# ----------------------------------------------------------------------
# 解析项目根路径（相对于本文件的两级父目录）并优先加载项目根目录下的 .env 文件。
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
environment.load_local_env_file(PROJECT_ROOT)

# ----------------------------------------------------------------------
# 2. 文件存储路径与上传限制
# ----------------------------------------------------------------------
# 路径定义为相对路径，由服务在项目根目录启动时解析。
# 原始文件、外部转换的中间文本（Docling）、清洗后文本及 staging 临时目录分目录存放，便于失败补偿与追溯。
BASE_STORAGE_DIR: Final[Path] = Path("storage")
RAW_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "raw"
RAW_LOCAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "local"
RAW_EXTERNAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "external"
SECONDARY_TEXT_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "secondary_text"
CLEANED_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "cleaned"
PROCESSING_STAGING_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "staging"
# 单个文件上传的最大大小限制（默认 20 MiB）
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

# ----------------------------------------------------------------------
# 3. 文档领域默认值与编号生成规则
# ----------------------------------------------------------------------
# 新上传文档的初始状态（默认为 uploaded）
DEFAULT_DOCUMENT_STATUS: Final[str] = DocumentStatus.UPLOADED.value
# 初始文档版本号
DEFAULT_DOCUMENT_VERSION: Final[int] = 1
# 默认操作人/系统标识
DEFAULT_CREATED_BY_ACTOR_CODE: Final[str] = "knowledge_operator_001"
# 业务文档编号前缀（如 DOC2026...）及随机字符位数
DOCUMENT_CODE_PREFIX: Final[str] = "DOC"
DOCUMENT_CODE_RANDOM_LENGTH: Final[int] = 8

# ----------------------------------------------------------------------
# 4. 数据库与向量存储 (Qdrant) 配置
# ----------------------------------------------------------------------
# SQLAlchemy 数据库连接 URL（必填，生产环境通常为 MySQL，测试可配置独立库）
SQLALCHEMY_DATABASE_URL: Final[str] = environment.get_required_env(
    "SQLALCHEMY_DATABASE_URL"
)
# Qdrant 向量数据库服务地址与默认 Collection 名称
QDRANT_URL: Final[str] = environment.get_env(
    "QDRANT_URL",
    "http://127.0.0.1:6333",
)
QDRANT_COLLECTION_NAME: Final[str] = environment.get_env(
    "QDRANT_COLLECTION_NAME",
    "knowledge_chunks",
)

# ----------------------------------------------------------------------
# 5. 向量嵌入服务 (DashScope / Qwen Embedding)
# ----------------------------------------------------------------------
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
# 向量维度（默认 1024 维）
EMBEDDING_VECTOR_SIZE: Final[int] = environment.get_int_env(
    "EMBEDDING_VECTOR_SIZE",
    1024,
)
# 向量生成分批大小（单次请求处理的切块数量）
EMBEDDING_BATCH_SIZE: Final[int] = environment.get_int_env(
    "EMBEDDING_BATCH_SIZE",
    10,
)

# ----------------------------------------------------------------------
# 6. 大语言模型服务 (DeepSeek Agent LLM)
# ----------------------------------------------------------------------
# 用于历史 Context Read Set 选择、Planner 任务编排与 Document Executor Agents。
DEEPSEEK_API_KEY: Final[str | None] = environment.get_optional_env(
    "DEEPSEEK_API_KEY"
)
DEEPSEEK_BASE_URL: Final[str] = environment.get_env(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com",
)
# 严格 Tool 调用模式的 Base URL（DeepSeek beta 接口）
DEEPSEEK_STRICT_TOOL_BASE_URL: Final[str] = environment.get_env(
    "DEEPSEEK_STRICT_TOOL_BASE_URL",
    "https://api.deepseek.com/beta",
)
DEEPSEEK_MODEL_NAME: Final[str] = environment.get_env(
    "DEEPSEEK_MODEL_NAME",
    "deepseek-v4-flash",
)
# LLM 单次调用超时时间（秒）与最大重试次数
DEEPSEEK_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "DEEPSEEK_TIMEOUT_SECONDS",
    60,
)
DEEPSEEK_MAX_RETRIES: Final[int] = environment.get_int_env(
    "DEEPSEEK_MAX_RETRIES",
    2,
)

# ----------------------------------------------------------------------
# 7. Redis 缓存与分布式锁配置 (Context & Runtime)
# ----------------------------------------------------------------------
# 应用生命周期持有一个全局异步 Redis 客户端，路由并发锁与热资源队列共享此连接池。
REDIS_URL: Final[str] = environment.get_env(
    "REDIS_URL",
    "redis://127.0.0.1:6379/0",
)
# Redis 套接字连接与读写超时（秒）
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
# 每条上下文链在 Redis 中维护的热资源队列最大容量（采用刷新式 FIFO，默认 16）
CONTEXT_RESOURCE_QUEUE_MAX_SIZE: Final[int] = environment.get_int_env(
    "CONTEXT_RESOURCE_QUEUE_MAX_SIZE",
    16,
)

# ----------------------------------------------------------------------
# 8. 文档转换解析服务 (Docling)
# ----------------------------------------------------------------------
# 复杂办公格式（pdf/doc/docx/ppt/pptx）先由 Docling 转换为 Markdown，之后复用本地 Markdown 清洗切块流水线。
DOCING_SOURCE_TYPES: Final[set[str]] = {"pdf", "doc", "docx", "ppt", "pptx"}
LOCAL_MARKDOWN_SOURCE_TYPES: Final[set[str]] = {"md"}
LOCAL_TEXT_SOURCE_TYPES: Final[set[str]] = {"txt"}
LOCAL_TABLE_SOURCE_TYPES: Final[set[str]] = {"csv"}
# Docling 转换服务地址与接口端点
DOCLING_SERVER_URL: Final[str] = environment.get_env(
    "DOCLING_SERVER_URL",
    "http://115.29.238.225:5001",
)
DOCLING_CONVERT_ENDPOINT: Final[str] = f"{DOCLING_SERVER_URL}/v1/convert/file"
# Docling 单文档转换超时时间（秒）及目标输出格式
DOCLING_TIMEOUT_SECONDS: Final[int] = environment.get_int_env(
    "DOCLING_TIMEOUT_SECONDS",
    180,
)
DOCLING_OUTPUT_TYPE: Final[str] = environment.get_env("DOCLING_OUTPUT_TYPE", "md")

# ----------------------------------------------------------------------
# 9. 本地结构化日志与可观测性存储目录 (JSONL)
# ----------------------------------------------------------------------
# 日志存储根目录（相对路径始终按项目根目录解析）
_configured_log_storage_dir = Path(
    environment.get_env("LOG_STORAGE_DIR", "logs")
)
LOG_STORAGE_DIR: Final[Path] = (
    _configured_log_storage_dir
    if _configured_log_storage_dir.is_absolute()
    else PROJECT_ROOT / _configured_log_storage_dir
)
# 文档生命周期各阶段结构化日志目录
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
# Agent Tool 审计日志与 Context 可观测性日志目录
AGENT_TOOL_LOG_DIR: Final[Path] = LOG_STORAGE_DIR / "agent_tools"
CONTEXT_OBSERVABILITY_LOG_DIR: Final[Path] = LOG_STORAGE_DIR / "context"
