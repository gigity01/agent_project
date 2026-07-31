"""应用级对象容器。"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.agents.context_agent import ContextAgentRouter
from app.agents.deepseek_provider import DeepSeekModelProvider
from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
)
from app.integrations.redis_client import close_redis_client
from app.modules.context.application.context_service import ContextService
from app.modules.context.application.resource_service import (
    ContextResourceService,
)


@dataclass
class AppContainer:
    """集中持有应用生命周期内共享的对象。"""

    redis_client: Redis
    deepseek_provider: DeepSeekModelProvider | None
    context_agent_router: ContextAgentRouter | None
    context_route_lock_manager: ConversationRouteLockManager
    context_resource_service: ContextResourceService
    context_service: ContextService

    async def aclose(self) -> None:
        """按依赖顺序释放外部客户端。"""
        try:
            if self.deepseek_provider is not None:
                await self.deepseek_provider.aclose()
        finally:
            await close_redis_client(self.redis_client)
