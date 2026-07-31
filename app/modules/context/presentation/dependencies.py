"""Context FastAPI 请求依赖。"""

from fastapi import Depends, Request

from app.bootstrap.container import AppContainer
from app.modules.context.application.context_service import ContextService


def get_container(request: Request) -> AppContainer:
    """获取应用生命周期内装配完成的统一容器。"""
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, AppContainer):
        raise RuntimeError("应用容器尚未初始化")
    return container


def get_context_service(
    container: AppContainer = Depends(get_container),
) -> ContextService:
    """获取共享的 Context Service。"""
    return container.context_service


def get_context_routing_service(
    container: AppContainer = Depends(get_container),
) -> ContextService:
    """获取已配置 Context Router 的 Context Service。"""
    if container.context_agent_router is None:
        raise RuntimeError("Agent 功能未配置 DEEPSEEK_API_KEY")
    return container.context_service
