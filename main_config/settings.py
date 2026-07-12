# =======================================================
# obs_upload

# document_upload_started
# document_upload_raw_file_saved
# document_upload_hash_calculated
# document_upload_duplicate_detected
# document_upload_completed
# document_upload_failed

# =======================================================


"""本地结构化日志的目录配置。"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


LOG_STORAGE_DIR = BASE_DIR  / "logs"


DOCUMENT_LIFECYCLE_LOG_DIR = LOG_STORAGE_DIR / "document_lifecycle"

DOCUMENT_UPLOAD_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "upload"
DOCUMENT_PROCESS_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "process"
DOCUMENT_CHUNK_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "chunk"
DOCUMENT_INDEX_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "index"
DOCUMENT_RETRIEVAL_LOG_DIR = DOCUMENT_LIFECYCLE_LOG_DIR / "retrieval"

# C:\Users\yangs\Desktop\agent\agent-knowledge\logs
# C:\Users\yangs\Desktop\agent\agent-knowledge\logs\document_lifecycle\upload
# C:\Users\yangs\Desktop\agent\agent-knowledge\logs\document_lifecycle\upload

if __name__ == '__main__':
    print(BASE_DIR)
    print(LOG_STORAGE_DIR)
    print(DOCUMENT_UPLOAD_LOG_DIR)
