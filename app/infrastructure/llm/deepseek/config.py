"""DeepSeek Provider 专用配置常量重导出模块。

职责说明：
- 从 `app.config.settings` 导入并集中暴露 DeepSeek LLM 客户端所需的关键配置（API Key、Base URL、Strict Tool URL、模型名、超时与重试次数）。
"""

from app.config.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MAX_RETRIES,
    DEEPSEEK_MODEL_NAME,
    DEEPSEEK_STRICT_TOOL_BASE_URL,
    DEEPSEEK_TIMEOUT_SECONDS,
)

__all__ = [
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MAX_RETRIES",
    "DEEPSEEK_MODEL_NAME",
    "DEEPSEEK_STRICT_TOOL_BASE_URL",
    "DEEPSEEK_TIMEOUT_SECONDS",
]
