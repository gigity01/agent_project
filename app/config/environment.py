"""应用环境变量加载与安全校验工具模块。"""

import os
from pathlib import Path


def load_local_env_file(project_root: Path) -> None:
    """读取项目根目录的 `.env` 文件并将变量载入 `os.environ`，且不覆盖系统已注入的变量。"""
    system_environment_keys = set(os.environ)
    env_file = project_root / ".env"
    if not env_file.is_file():
        return

    # 逐行解析 .env 文件
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # 跳过空行与注释行
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        # 去除首尾成对的引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        # 仅在系统环境变量不存在该 key 时注入
        if key and key not in system_environment_keys:
            os.environ[key] = value


def get_required_env(name: str) -> str:
    """读取必填环境变量，缺失或仍为默认占位符时抛出异常。"""
    value = os.getenv(name)
    if not value or value.startswith("replace-with-"):
        raise RuntimeError(f"缺少必填环境变量: {name}")
    return value


def get_optional_env(name: str) -> str | None:
    """读取可选环境变量，未配置或仍为占位符时返回 None。"""
    value = os.getenv(name)
    if not value or value.startswith("replace-with-"):
        return None
    return value


def get_env(name: str, default: str) -> str:
    """读取环境变量，若未配置或为空则返回指定的默认值。"""
    return os.getenv(name) or default


def get_int_env(name: str, default: int) -> int:
    """读取整数类型的环境变量，并在格式非法时抛出带有变量名的异常。"""
    value = os.getenv(name)
    if not value:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"环境变量必须是整数: {name}") from exc
