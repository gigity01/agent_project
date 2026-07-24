"""OpenAI Agents SDK 的 DeepSeek 模型 Provider。"""

from __future__ import annotations

from dataclasses import dataclass

from agents import (
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
)
from openai import AsyncOpenAI

from app.app_config.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MAX_RETRIES,
    DEEPSEEK_MODEL_NAME,
    DEEPSEEK_TIMEOUT_SECONDS,
)


@dataclass
class DeepSeekModelProvider:
    """持有 DeepSeek 客户端、模型适配器与默认模型参数。"""

    client: AsyncOpenAI
    model: OpenAIChatCompletionsModel
    model_settings: ModelSettings

    @classmethod
    def create(cls) -> "DeepSeekModelProvider":
        """创建使用 DeepSeek Chat Completions 的模型 Provider。"""
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")

        client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=DEEPSEEK_TIMEOUT_SECONDS,
            max_retries=DEEPSEEK_MAX_RETRIES,
        )

        model = OpenAIChatCompletionsModel(
            model=DEEPSEEK_MODEL_NAME,
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
            model=model,
            model_settings=model_settings,
        )

    async def aclose(self) -> None:
        """释放底层异步 HTTP 连接池。"""
        await self.client.close()


def build_deepseek_run_config(
    provider: DeepSeekModelProvider,
) -> RunConfig:
    """构建一次 Agent 执行使用的 DeepSeek 模型与追踪策略。"""
    return RunConfig(
        model=provider.model,
        model_settings=provider.model_settings,
        tracing_disabled=True,
    )
