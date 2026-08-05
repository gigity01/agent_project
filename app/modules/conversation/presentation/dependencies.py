"""Conversation Orchestration FastAPI 依赖。"""

from fastapi import Depends, HTTPException

from app.bootstrap.container import AppContainer
from app.bootstrap.dependencies import get_container


def get_send_conversation_message(
    container: AppContainer = Depends(get_container),
):
    if (
        container.context_agent_router is None
        or container.send_conversation_message is None
    ):
        raise HTTPException(status_code=503, detail="Conversation Agent 服务未配置")
    return container.send_conversation_message


def get_turn_status(
    container: AppContainer = Depends(get_container),
):
    return container.get_turn_status
