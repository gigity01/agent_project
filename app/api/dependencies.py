"""FastAPI 请求依赖。"""

from fastapi import Request

from app.agents.deepseek_provider import DeepSeekModelProvider


def get_deepseek_provider(request: Request) -> DeepSeekModelProvider:
    """获取应用生命周期内共享的 DeepSeek 模型 Provider。"""
    provider = getattr(request.app.state, "deepseek_provider", None)

    if not isinstance(provider, DeepSeekModelProvider):
        raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")

    return provider
