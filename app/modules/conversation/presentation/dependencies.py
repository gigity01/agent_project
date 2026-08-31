"""Conversation 表现层 FastAPI 依赖注入。"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.bootstrap.container import AppContainer
from app.bootstrap.dependencies import get_container


def get_send_conversation_message(
    container: AppContainer = Depends(get_container),
):
    """获取 SendConversationMessageUseCase 实例的依赖项。

    Args:
        container: 应用级 IoC 容器实例。

    Returns:
        SendConversationMessageUseCase 实例。

    Raises:
        HTTPException: 当 Context Agent 路由器或发送消息用例未在容器中正确配置时返回 503。
    """
    if (
        container.context_agent_router is None
        or container.send_conversation_message is None
    ):
        raise HTTPException(status_code=503, detail="Conversation Agent 服务未配置")
    return container.send_conversation_message


def get_turn_status(
    container: AppContainer = Depends(get_container),
):
    """获取 GetTurnStatusUseCase 实例的依赖项。

    Args:
        container: 应用级 IoC 容器实例。

    Returns:
        GetTurnStatusUseCase 实例。
    """
    return container.get_turn_status
