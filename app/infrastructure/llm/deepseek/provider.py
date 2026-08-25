"""OpenAI Agents SDK 与 DeepSeek 专用结构化输出客户端适配模块。

职责说明：
- 封装适配 DeepSeek API 的 `AsyncOpenAI` 客户端与 OpenAI Agents SDK `OpenAIChatCompletionsModel` 模型对象。
- 维护通用客户端与 Beta Strict Tool 客户端两个独立的连接通道。
- 提供 `DeepSeekModelProvider` 的工厂创建方法 `create()` 与优雅关闭方法 `aclose()`。
- 提供 `build_deepseek_run_config` 辅助函数生成标准的 `RunConfig`。
"""

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
    """持有通用 Agents SDK 客户端、Strict Tool 客户端与模型配置的提供者类。

    属性:
        client: 标准 DeepSeek API 异步客户端。
        strict_tool_client: DeepSeek Strict Tool 专用 Base URL 异步客户端。
        model: 适配 Agents SDK 的 OpenAIChatCompletionsModel 实例。
        model_name: 模型名称（如 `deepseek-v4-flash`）。
        model_settings: 模型默认运行参数配置（如关闭 thinking、关闭并行工具等）。
    """

    client: AsyncOpenAI
    strict_tool_client: AsyncOpenAI
    model: OpenAIChatCompletionsModel
    model_name: str
    model_settings: ModelSettings

    @classmethod
    def create(cls) -> "DeepSeekModelProvider":
        """工厂方法：创建并初始化 DeepSeek 异步客户端与 Agents SDK 模型适配器。

        返回:
            DeepSeekModelProvider: 初始化完成的 Provider 实例。

        异常:
            RuntimeError: 当未配置 DEEPSEEK_API_KEY 时抛出。
        """
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")

        client_options = {
            "api_key": DEEPSEEK_API_KEY,
            "timeout": DEEPSEEK_TIMEOUT_SECONDS,
            "max_retries": DEEPSEEK_MAX_RETRIES,
        }
        # 标准端点客户端
        client = AsyncOpenAI(
            base_url=DEEPSEEK_BASE_URL,
            **client_options,
        )
        # Strict Tool Beta 端点客户端
        strict_tool_client = AsyncOpenAI(
            base_url=DEEPSEEK_STRICT_TOOL_BASE_URL,
            **client_options,
        )

        # 封装为 OpenAI Agents SDK 适配模型对象
        model = OpenAIChatCompletionsModel(
            model=DEEPSEEK_MODEL_NAME,
            openai_client=client,
            strict_feature_validation=True,
            buffer_streamed_tool_calls=True,
        )

        # 默认模型参数：限制 max_tokens、关闭并行 tool_calls 并禁用 thinking 模式
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
        """异步优雅关闭两个 HTTP 客户端底层持有的连接池。"""
        await self.client.close()
        await self.strict_tool_client.close()


def build_deepseek_run_config(
    provider: DeepSeekModelProvider,
) -> RunConfig:
    """构建用于驱动普通 Agents SDK Agent 的 DeepSeek 运行配置对象。

    参数:
        provider: DeepSeek 模型提供者实例。

    返回:
        RunConfig: 绑定了 model 与 model_settings 的运行配置。
    """
    return RunConfig(
        model=provider.model,
        model_settings=provider.model_settings,
        tracing_disabled=True,
    )
