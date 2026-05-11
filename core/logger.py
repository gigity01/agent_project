import logging
from logging.handlers import RotatingFileHandler
import os

# 确保日志文件夹存在
LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger():
    logger = logging.getLogger("KnowledgeAgent")
    logger.setLevel(logging.INFO)
    # 防止重复添加处理器
    if logger.handlers:
        return logger

    # 日志格式：时间 - 级别 - 信息
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 滚动日志：单个日志最大10MB，保留5个备份
    file_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "processors.log"),
        maxBytes=15 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台也打印日志
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# 全局唯一日志实例，全项目通用
logger = setup_logger()