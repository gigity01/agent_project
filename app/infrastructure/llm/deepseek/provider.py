"""OpenAI Agents SDK 与 DeepSeek 专用结构化输出客户端。"""

from __future__ import annotations

from dataclasses import dataclass

from agents import (
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
)
from openai import AsyncOpenAI

from app.infrastructure.llm.deepseek.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MAX_RETRIES,
    DEEPSEEK_MODEL_NAME,
    DEEPSEEK_STRICT_TOOL_BASE_URL,
    DEEPSEEK_TIMEOUT_SECONDS,
)


@dataclass
class DeepSeekModelProvider:
    """持有通用 Agents SDK 客户端和 strict tool 客户端。"""

    client: AsyncOpenAI
    strict_tool_client: AsyncOpenAI
    model: OpenAIChatCompletionsModel
    model_name: str
    model_settings: ModelSettings

    @classmethod
    def create(cls) -> "DeepSeekModelProvider":
        """创建通用模型适配器及 DeepSeek strict tool 专用客户端。"""
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")

        client_options = {
            "api_key": DEEPSEEK_API_KEY,
            "timeout": DEEPSEEK_TIMEOUT_SECONDS,
            "max_retries": DEEPSEEK_MAX_RETRIES,
        }
        client = AsyncOpenAI(
            base_url=DEEPSEEK_BASE_URL,
            **client_options,
        )
        strict_tool_client = AsyncOpenAI(
            base_url=DEEPSEEK_STRICT_TOOL_BASE_URL,
            **client_options,
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
            strict_tool_client=strict_tool_client,
            model=model,
            model_name=DEEPSEEK_MODEL_NAME,
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
