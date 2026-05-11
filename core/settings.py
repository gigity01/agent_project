import os

# 项目根目录
BASE_DIR = os.path.abspath(os.getcwd())

# 目录配置
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")         # 原始文件
CLEANED_DIR = os.path.join(BASE_DIR, "cleaned_files")# 清洗后文件
LOG_DIR = os.path.join(BASE_DIR, "logs")              # 日志目录

# 支持的文件后缀（当前只开放 txt csv）
SUPPORTED_SUFFIXES = {".txt", ".csv", ".md", ".pdf"}


VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")


os.makedirs(VECTOR_DB_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CLEANED_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)