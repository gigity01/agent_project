"""Context 兼容 Router 导出。"""

from app.modules.context.presentation.router import (
    complete_context_turn,
    legacy_router as router,
    route_context,
)


__all__ = [
    "complete_context_turn",
    "route_context",
    "router",
]
