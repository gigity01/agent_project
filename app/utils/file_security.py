"""上传文件名、类型校验和内容哈希计算工具。"""

from pathlib import Path
import hashlib

from fastapi import HTTPException, UploadFile

from app.app_config.settings import (
    ALLOWED_EXTENSIONS,
    ALLOWED_CONTENT_TYPES,
)


def validate_filename(filename: str) -> None:
    """拒绝空文件名及可能导致路径穿越的危险字符。"""
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    dangerous_chars = ["..", "/", "\\", "\x00"]

    if any(char in filename for char in dangerous_chars):
        raise HTTPException(
            status_code=400,
            detail="文件名包含非法字符"
        )


def get_safe_extension(filename: str) -> str:
    """验证文件名后返回已在白名单中的小写扩展名。"""
    validate_filename(filename)

    if "." not in filename:
        raise HTTPException(status_code=400, detail="文件必须包含扩展名")

    ext = filename.rsplit(".", 1)[-1].lower().strip()

    if f".{ext}" not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：{ext}"
        )

    return ext


def validate_content_type(file: UploadFile) -> None:
    """校验客户端声明的 Content-Type 是否处于允许范围。"""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 Content-Type: {file.content_type}"
        )


def calculate_file_hash(file_path: Path) -> str:
    """以流式读取方式计算文件 SHA-256，避免大文件占满内存。"""
    sha256 = hashlib.sha256()

    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()
