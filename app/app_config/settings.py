"""应用的文件存储、外部服务与处理参数配置。"""

import os
from pathlib import Path
from typing import Final


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"


def _load_local_env_file() -> None:
    """读取本地 `.env`，且不覆盖已由部署环境注入的变量。"""
    if not ENV_FILE.is_file():
        return

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key:
            os.environ.setdefault(key, value)


def _get_required_env(name: str) -> str:
    """读取必填环境变量，并在缺失时给出不包含敏感值的错误。"""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"缺少必填环境变量: {name}")
    return value


_load_local_env_file()

# 文件上传与派生产物存储。
BASE_STORAGE_DIR: Final[Path] = Path("storage")
RAW_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "raw"
RAW_LOCAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "local"
RAW_EXTERNAL_STORAGE_DIR: Final[Path] = RAW_STORAGE_DIR / "external"
SECONDARY_TEXT_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "secondary_text"
CLEANED_STORAGE_DIR: Final[Path] = BASE_STORAGE_DIR / "cleaned"
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
DEFAULT_DOCUMENT_STATUS: Final[str] = "draft"
DEFAULT_DOCUMENT_VERSION: Final[int] = 1
DEFAULT_CREATED_BY_ACTOR_CODE: Final[str] = "knowledge_operator_001"
DOCUMENT_CODE_PREFIX: Final[str] = "DOC"
DOCUMENT_CODE_RANDOM_LENGTH: Final[int] = 8

# 数据库与检索服务。
SQLALCHEMY_DATABASE_URL: Final[str] = _get_required_env("SQLALCHEMY_DATABASE_URL")
CHILD_CHUNK_MAX_LEN: Final[int] = 600
QDRANT_URL: Final[str] = "http://127.0.0.1:6333"
QDRANT_COLLECTION_NAME: Final[str] = "knowledge_chunks"

# DashScope / Qwen Embedding。
DASHSCOPE_API_KEY: Final[str] = _get_required_env("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL: Final[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
EMBEDDING_MODEL_NAME: Final[str] = "text-embedding-v3"
EMBEDDING_VECTOR_SIZE: Final[int] = 1024
EMBEDDING_BATCH_SIZE: Final[int] = 10

# 文档转换服务。
DOCING_SOURCE_TYPES: Final[set[str]] = {"pdf", "doc", "docx", "ppt", "pptx"}
LOCAL_MARKDOWN_SOURCE_TYPES: Final[set[str]] = {"md"}
LOCAL_TEXT_SOURCE_TYPES: Final[set[str]] = {"txt"}
LOCAL_TABLE_SOURCE_TYPES: Final[set[str]] = {"csv"}
DOCLING_SERVER_URL: Final[str] = "http://115.29.238.225:5001"
DOCLING_CONVERT_ENDPOINT: Final[str] = f"{DOCLING_SERVER_URL}/convert"
DOCLING_TIMEOUT_SECONDS: Final[int] = 180
DOCLING_OUTPUT_TYPE: Final[str] = "md"
