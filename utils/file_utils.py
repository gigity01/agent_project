import os
import uuid

from core.logger import logger
from core.settings import SUPPORTED_SUFFIXES, CLEANED_DIR, UPLOAD_DIR


def is_safe_file_path(file_path: str) -> bool:
    real_path = os.path.abspath(file_path)
    # 强制限定只能在上传目录，防路径穿越/绝对路径绕过
    if not real_path.startswith(os.path.abspath(UPLOAD_DIR)):
        logger.error(f"安全拦截：文件不在允许目录内 -> {real_path}")
        return False

    if not os.path.exists(real_path):
        logger.error(f"文件不存在 -> {real_path}")
        return False

    if not os.path.isfile(real_path):
        logger.error(f"不是合法文件 -> {real_path}")
        return False

    suffix = os.path.splitext(real_path)[-1].lower()
    if suffix not in SUPPORTED_SUFFIXES:
        logger.error(f"不支持的文件后缀 -> {suffix}")
        return False

    return True


def get_safe_filename(origin_suffix: str) -> str:
    """生成安全文件名"""
    return f"{uuid.uuid4()}{origin_suffix}"


def save_cleaned_file(content: str, origin_suffix: str) -> str | None:
    """保存清洗后文件到 cleaned_files，返回最终路径"""
    if not content.strip():
        logger.warning("清洗后内容为空，跳过保存")
        return None

    safe_name = get_safe_filename(origin_suffix)
    save_path = os.path.join(CLEANED_DIR, safe_name)

    try:
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"清洗文件保存成功 -> {save_path}")
        return save_path
    except Exception as e:
        logger.error("清洗文件保存失败", exc_info=True)
        return None
