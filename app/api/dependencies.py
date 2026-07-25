"""FastAPI 请求依赖。"""

from fastapi import Depends, Request

from app.agents.context_agent import ContextAgentRouter
from app.agents.deepseek_provider import DeepSeekModelProvider
from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
)


def get_deepseek_provider(request: Request) -> DeepSeekModelProvider:
    """获取应用生命周期内共享的 DeepSeek 模型 Provider。"""
    provider = getattr(request.app.state, "deepseek_provider", None)

    if not isinstance(provider, DeepSeekModelProvider):
        raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")

    return provider


def get_context_agent_router(
    provider: DeepSeekModelProvider = Depends(get_deepseek_provider),
) -> ContextAgentRouter:
    """基于应用共享 Provider 构造无状态 Context Agent 路由器。"""
    return ContextAgentRouter(provider)


def get_context_route_lock_manager(
    request: Request,
) -> ConversationRouteLockManager:
    """获取由应用外部注入的 Redis Conversation 路由锁管理器。"""
    manager = getattr(
        request.app.state,
        "context_route_lock_manager",
        None,
    )
    if not isinstance(manager, ConversationRouteLockManager):
        raise RuntimeError("Context 路由锁客户端尚未注入")
    return manager
