"""OpenAI Agents SDK 与 DeepSeek 专用结构化输出客户端。"""

from __future__ import annotations

from dataclasses import dataclass

from agents import (
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
)
from openai import AsyncOpenAI

from app.app_config import settings


def _build_strict_tool_base_url(base_url: str) -> str:
    """将 DeepSeek 普通端点转换为 strict tool beta 端点。"""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/beta"):
        return normalized
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/beta"


@dataclass
class DeepSeekModelProvider:
    """持有通用 Agents SDK 客户端和 Context strict tool 客户端。"""

    client: AsyncOpenAI
    strict_tool_client: AsyncOpenAI
    model: OpenAIChatCompletionsModel
    model_name: str
    model_settings: ModelSettings

    @classmethod
    def create(cls) -> "DeepSeekModelProvider":
        """创建通用模型适配器及 DeepSeek strict tool 专用客户端。"""
        if not settings.DEEPSEEK_API_KEY:
            raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")

        client_options = {
            "api_key": settings.DEEPSEEK_API_KEY,
            "timeout": settings.DEEPSEEK_TIMEOUT_SECONDS,
            "max_retries": settings.DEEPSEEK_MAX_RETRIES,
        }
        client = AsyncOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            **client_options,
        )
        strict_tool_client = AsyncOpenAI(
            base_url=_build_strict_tool_base_url(
                settings.DEEPSEEK_BASE_URL
            ),
            **client_options,
        )

        model = OpenAIChatCompletionsModel(
            model=settings.DEEPSEEK_MODEL_NAME,
            openai_client=client,
            strict_feature_validation=True,
            buffer_streamed_tool_calls=True,
        )

        model_settings = ModelSettings(
            max_tokens=512,
            parallel_tool_calls=False,
            extra_body={
                "thinking": {
                    "type": "disabled",
                }
            },
        )

        return cls(
            client=client,
            strict_tool_client=strict_tool_client,
            model=model,
            model_name=settings.DEEPSEEK_MODEL_NAME,
            model_settings=model_settings,
        )

    async def aclose(self) -> None:
        """释放两个异步 HTTP 客户端持有的连接池。"""
        await self.client.close()
        await self.strict_tool_client.close()


def build_deepseek_run_config(
    provider: DeepSeekModelProvider,
) -> RunConfig:
    """构建普通 Agents SDK Agent 使用的 DeepSeek 运行配置。"""
    return RunConfig(
        model=provider.model,
        model_settings=provider.model_settings,
        tracing_disabled=True,
    )
