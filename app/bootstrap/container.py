"""应用级对象容器。"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.infrastructure.llm.deepseek.provider import DeepSeekModelProvider
from app.infrastructure.redis.client import close_redis_client
from app.modules.context.infrastructure.llm.deepseek_router import (
    DeepSeekContextRouter,
)
from app.modules.context.infrastructure.locking.redis_conversation_lock import (
    ConversationRouteLockManager,
)
from app.modules.context.application.context_service import ContextService
from app.modules.context.application.resource_service import (
    ContextResourceService,
)
from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksUseCase,
)
from app.modules.document.application.use_cases.index_vectors import (
    IndexVectorsUseCase,
)
from app.modules.document.application.use_cases.process_document import (
    ProcessDocumentUseCase,
)
from app.modules.document.application.use_cases.upload_document import (
    UploadDocumentUseCase,
)


@dataclass
class AppContainer:
    """集中持有应用生命周期内共享的对象。"""

    redis_client: Redis
    deepseek_provider: DeepSeekModelProvider | None
    context_agent_router: DeepSeekContextRouter | None
    context_route_lock_manager: ConversationRouteLockManager
    context_resource_service: ContextResourceService
    context_service: ContextService
    upload_document: UploadDocumentUseCase
    process_document: ProcessDocumentUseCase
    build_chunks: BuildChunksUseCase
    index_vectors: IndexVectorsUseCase

    async def aclose(self) -> None:
        """按依赖顺序释放外部客户端。"""
        try:
            if self.deepseek_provider is not None:
                await self.deepseek_provider.aclose()
        finally:
            await close_redis_client(self.redis_client)
