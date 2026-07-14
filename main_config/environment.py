"""共享的本地环境变量加载与校验工具。"""

import os
from pathlib import Path


def load_local_env_file(project_root: Path) -> None:
    """读取项目根目录的 ``.env``，且不覆盖系统已注入的变量。"""
    system_environment_keys = set(os.environ)
    env_file = project_root / ".env"
    if not env_file.is_file():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key and key not in system_environment_keys:
            os.environ[key] = value


def get_required_env(name: str) -> str:
    """读取必填环境变量，缺失时不泄露任何配置值。"""
    value = os.getenv(name)
    if not value or value.startswith("replace-with-"):
        raise RuntimeError(f"缺少必填环境变量: {name}")
    return value


def get_env(name: str, default: str) -> str:
    """读取可选环境变量，空值时采用默认值。"""
    return os.getenv(name) or default


def get_int_env(name: str, default: int) -> int:
    """读取整数环境变量，并在格式错误时给出变量名。"""
    value = os.getenv(name)
    if not value:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"环境变量必须是整数: {name}") from exc
