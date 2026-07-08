from pathlib import Path
import hashlib

from fastapi import HTTPException, UploadFile

from app.app_config.settings import (
    ALLOWED_EXTENSIONS,
    ALLOWED_CONTENT_TYPES,
)


def validate_filename(filename: str) -> None:
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    dangerous_chars = ["..", "/", "\\", "\x00"]

    if any(char in filename for char in dangerous_chars):
        raise HTTPException(
            status_code=400,
            detail="文件名包含非法字符"
        )


def get_safe_extension(filename: str) -> str:
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
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 Content-Type: {file.content_type}"
        )


def calculate_file_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()
