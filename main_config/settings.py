"""本地结构化日志的目录配置。

所有观测组件都从本模块取得目录，避免上传、处理、切块等阶段把同一次
文档生命周期的日志写到不同位置。``LOG_STORAGE_DIR`` 可使用绝对路径，
也可使用相对于项目根目录的路径。
"""

from pathlib import Path

from main_config import environment

BASE_DIR = Path(__file__).resolve().parent.parent
environment.load_local_env_file(BASE_DIR)

# 优先接受部署环境给出的绝对路径；相对路径始终以项目根目录为基准，
# 从而不受启动命令所在工作目录影响。
_configured_log_storage_dir = Path(environment.get_env("LOG_STORAGE_DIR", "logs"))
LOG_STORAGE_DIR = (
    _configured_log_storage_dir
    if _configured_log_storage_dir.is_absolute()
    else BASE_DIR / _configured_log_storage_dir
)


DOCUMENT_LIFECYCLE_LOG_DIR = LOG_STORAGE_DIR / "document_lifecycle"

DOCUMENT_UPLOAD_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "upload"
DOCUMENT_PROCESS_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "process"
DOCUMENT_CHUNK_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "chunk"
DOCUMENT_INDEX_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "index"
DOCUMENT_RETRIEVAL_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "retrieval"

if __name__ == '__main__':
    # 仅供本地排查路径解析结果，不参与应用启动流程。
    print(BASE_DIR)
    print(LOG_STORAGE_DIR)
    print(DOCUMENT_UPLOAD_LOG_DIR)
