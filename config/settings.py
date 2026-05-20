import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ====================== 基础路径配置（完全适配你的目录结构） ======================
# 当前文件在 config/ 目录下，BASE_DIR 自动指向项目根目录 agent-knowledge
BASE_DIR = Path(__file__).parent.parent.absolute()

# 业务目录（你已存在的目录直接复用）
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")          # 原始上传文件目录
CLEANED_FILES_DIR = os.path.join(BASE_DIR, "cleaned_files") # 清洗后文件保存目录
VECTOR_DB_PATH = os.path.join(BASE_DIR, "chroma_db")     # 向量库持久化目录（你已存在）
LOGS_DIR = os.path.join(BASE_DIR, "logs")                 # 日志目录（你已存在）
CONFIG_DIR = os.path.join(BASE_DIR, "config")

# 新增：知识库台账目录（需在根目录新建 metadata 文件夹）
METADATA_DIR = os.path.join(BASE_DIR, "metadata")
KB_LIST_PATH = os.path.join(METADATA_DIR, "knowledge_list.json")

# ====================== 文件支持配置 ======================
SUPPORT_FILE_TYPES = {".md", ".txt", ".csv", ".pdf"}

# ====================== 分块配置 ======================
CHILD_CHUNK_MAX_LEN = 200
PARENT_CHUNK_MAX_LEN = 800
MAX_READ_SIZE = 1024 * 1024

# ====================== 向量&检索配置 ======================
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
DEFAULT_TOP_K = 5
HYBRID_WEIGHT_VECTOR = 0.6
HYBRID_WEIGHT_BM25 = 0.4

# ====================== 知识库状态枚举 ======================
KB_STATUS_ACTIVE = "active"
KB_STATUS_DELETED = "deleted"
KB_STATUS_REPLACED = "replaced"

# ====================== Redis 状态机配置（后续用） ======================
REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_DB = 0
PENDING_KEY_PREFIX = "kb_agent:pending:"

# ====================== Celery 异步配置（后续用） ======================
CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/0"

# ====================== API 密钥（你要求的环境变量） ======================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# ====================== 自动初始化必要目录 ======================
def init_dirs():
    # 只创建你还没有的目录（metadata），已存在的不会重复创建
    required_dirs = [METADATA_DIR]
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

# 项目启动时自动初始化
init_dirs()