"""FastAPI 请求依赖。"""

from fastapi import Depends, Request

from app.agents.context_agent import ContextAgentRouter
from app.agents.deepseek_provider import DeepSeekModelProvider
from app.bootstrap.container import AppContainer
from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
)
from app.services.context_resource_service import ContextResourceService
from app.services.context_service import ContextService


def get_container(request: Request) -> AppContainer:
    """获取应用生命周期内装配完成的统一容器。"""
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, AppContainer):
        raise RuntimeError("应用容器尚未初始化")
    return container


def get_deepseek_provider(
    container: AppContainer = Depends(get_container),
) -> DeepSeekModelProvider:
    """获取应用生命周期内共享的 DeepSeek 模型 Provider。"""
    provider = container.deepseek_provider

    if not isinstance(provider, DeepSeekModelProvider):
        raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")

    return provider


def get_context_agent_router(
    container: AppContainer = Depends(get_container),
) -> ContextAgentRouter:
    """获取应用容器中的 Context Agent Router。"""
    router = container.context_agent_router
    if not isinstance(router, ContextAgentRouter):
        raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")
    return router


def get_context_route_lock_manager(
    container: AppContainer = Depends(get_container),
) -> ConversationRouteLockManager:
    """获取应用生命周期内共享的 Redis Conversation 路由锁管理器。"""
    return container.context_route_lock_manager


def get_context_resource_service(
    container: AppContainer = Depends(get_container),
) -> ContextResourceService:
    """获取应用生命周期内共享的 Context 热资源服务。"""
    return container.context_resource_service


def get_context_service(
    container: AppContainer = Depends(get_container),
) -> ContextService:
    """获取应用生命周期内共享的 Context Service。"""
    return container.context_service


def get_context_routing_service(
    container: AppContainer = Depends(get_container),
) -> ContextService:
    """获取已配置 Context Router 的 Context Service。"""
    if container.context_agent_router is None:
        raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")
    return container.context_service
