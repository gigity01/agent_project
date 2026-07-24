"""OpenAI Agents SDK 的 DeepSeek 运行时配置。"""

from __future__ import annotations

from dataclasses import dataclass

from agents import (
    ModelSettings,
    OpenAIChatCompletionsModel,
    set_tracing_disabled,
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
class AgentRuntime:
    """持有 Agent 共用的 DeepSeek 客户端与模型实例。"""

    client: AsyncOpenAI
    model: OpenAIChatCompletionsModel
    default_model_settings: ModelSettings

    @classmethod
    def create(cls) -> "AgentRuntime":
        """创建使用 DeepSeek Chat Completions 的共享运行时。"""
        # 当前没有使用 OpenAI Platform API Key，不向 OpenAI tracing
        # 后端发送执行轨迹。
        set_tracing_disabled(True)

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
            default_model_settings=model_settings,
        )

    async def aclose(self) -> None:
        """释放底层异步 HTTP 连接池。"""
        await self.client.close()
