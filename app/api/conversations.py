"""Conversation 兼容 Router 导出。"""

from app.modules.context.presentation.router import (
    router,
    send_conversation_message,
)


__all__ = [
    "router",
    "send_conversation_message",
]
