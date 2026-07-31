"""Context FastAPI 依赖兼容导出。"""

from app.modules.context.presentation.dependencies import (
    get_container,
    get_context_agent_router,
    get_context_resource_service,
    get_context_route_lock_manager,
    get_context_routing_service,
    get_context_service,
    get_deepseek_provider,
)


__all__ = [
    "get_container",
    "get_context_agent_router",
    "get_context_resource_service",
    "get_context_route_lock_manager",
    "get_context_routing_service",
    "get_context_service",
    "get_deepseek_provider",
]
