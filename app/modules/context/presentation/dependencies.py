"""Context FastAPI 请求依赖注入定义。"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.bootstrap.container import AppContainer
from app.bootstrap.dependencies import get_container
from app.modules.context.application.context_service import ContextService


def get_context_service(
    container: AppContainer = Depends(get_container),
) -> ContextService:
    """获取共享的 ContextService 实例。

    Args:
        container: 应用级依赖注入容器。

    Returns:
        ContextService: 共享应用服务实例。
    """
    return container.context_service


def get_context_routing_service(
    container: AppContainer = Depends(get_container),
) -> ContextService:
    """获取已配置 Context Router 的 ContextService 实例。

    Args:
        container: 应用级依赖注入容器。

    Returns:
        ContextService: 共享应用服务实例。

    Raises:
        HTTPException: 若未配置 Context Agent Router，抛出 HTTP 503 异常。
    """
    if container.context_agent_router is None:
        raise HTTPException(
            status_code=503,
            detail="Context Agent 服务未配置",
        )
    return container.context_service
