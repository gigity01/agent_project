"""Context FastAPI 请求依赖。"""

from fastapi import Depends, HTTPException

from app.bootstrap.container import AppContainer
from app.bootstrap.dependencies import get_container
from app.modules.context.application.context_service import ContextService


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
        raise HTTPException(
            status_code=503,
            detail="Context Agent 服务未配置",
        )
    return container.context_service
