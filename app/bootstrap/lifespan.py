"""FastAPI 应用生命周期与对象装配。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from qdrant_client.models import PointStruct
from sqlalchemy.exc import IntegrityError

from app.config.settings import (
    CONTEXT_RESOURCE_QUEUE_MAX_SIZE,
    CONTEXT_ROUTE_LOCK_BLOCKING_TIMEOUT_SECONDS,
    CONTEXT_ROUTE_LOCK_TIMEOUT_SECONDS,
    DEEPSEEK_API_KEY,
    REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
    REDIS_SOCKET_TIMEOUT_SECONDS,
    REDIS_URL,
)
from app.bootstrap.container import AppContainer
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.infrastructure.llm.deepseek.provider import DeepSeekModelProvider
from app.infrastructure.redis.client import (
    close_redis_client,
    create_redis_client,
    ping_redis_client,
)
from app.modules.context.infrastructure.cache.redis_resource_queue import (
    ContextResourceQueueRepository,
)
from app.modules.context.infrastructure.llm.deepseek_router import (
    DeepSeekContextRouter,
)
from app.modules.context.infrastructure.locking.redis_conversation_lock import (
    ConversationRouteLockManager,
)
from app.modules.context.infrastructure.persistence.mapper import (
    SQLAlchemyContextRecordFactory,
    build_context_chain,
)
from app.modules.context.application.context_service import ContextService
from app.modules.context.application.resource_service import (
    ContextResourceService,
)
from app.modules.document.application.ports import (
    DocumentApplicationPorts,
    configure_document_ports,
)
from app.modules.document.infrastructure.chunking.factory import get_chunker
from app.modules.document.infrastructure.embedding.dashscope import (
    EmbeddingService,
)
from app.modules.document.infrastructure.parsing.docling_client import (
    DoclingClient,
)
from app.modules.document.infrastructure.parsing.factory import get_processor
from app.modules.document.infrastructure.persistence.models.child_chunk import (
    ChildChunk,
)
from app.modules.document.infrastructure.persistence.models.document import (
    Document,
)
from app.modules.document.infrastructure.persistence.models.parent_block import (
    ParentBlock,
)
from app.modules.document.infrastructure.storage.local import (
    calculate_file_hash,
    cleanup_file,
    get_safe_extension,
    validate_content_type,
)
from app.modules.document.infrastructure.vector_store.qdrant import (
    QdrantVectorStore,
)


async def build_container() -> AppContainer:
    """创建外部客户端并装配 Context 应用服务。"""
    redis_client = create_redis_client(
        REDIS_URL,
        socket_connect_timeout_seconds=(
            REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS
        ),
        socket_timeout_seconds=REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    deepseek_provider = None

    try:
        if not await ping_redis_client(redis_client):
            raise RuntimeError("Redis PING 未返回成功")

        route_lock_manager = ConversationRouteLockManager(
            redis_client,
            lock_timeout_seconds=CONTEXT_ROUTE_LOCK_TIMEOUT_SECONDS,
            blocking_timeout_seconds=(
                CONTEXT_ROUTE_LOCK_BLOCKING_TIMEOUT_SECONDS
            ),
        )
        queue_repository = ContextResourceQueueRepository(
            redis_client,
            capacity=CONTEXT_RESOURCE_QUEUE_MAX_SIZE,
        )
        record_factory = SQLAlchemyContextRecordFactory()
        resource_service = ContextResourceService(
            queue_repository=queue_repository,
            uow_factory=SQLAlchemyUnitOfWork,
            record_factory=record_factory,
        )
        deepseek_provider = (
            DeepSeekModelProvider.create()
            if DEEPSEEK_API_KEY is not None
            else None
        )
        agent_router = (
            DeepSeekContextRouter(deepseek_provider)
            if deepseek_provider is not None
            else None
        )
        context_service = ContextService(
            agent_router=agent_router,
            route_lock_manager=route_lock_manager,
            resource_service=resource_service,
            uow_factory=SQLAlchemyUnitOfWork,
            record_factory=record_factory,
            chain_mapper=build_context_chain,
        )
        configure_document_ports(
            DocumentApplicationPorts(
                uow_factory=SQLAlchemyUnitOfWork,
                document_factory=Document,
                parent_block_factory=ParentBlock,
                child_chunk_factory=ChildChunk,
                processor_factory=get_processor,
                chunker_factory=get_chunker,
                embedding_factory=EmbeddingService,
                vector_store_factory=QdrantVectorStore,
                docling_factory=DoclingClient,
                point_factory=PointStruct,
                validate_content_type=validate_content_type,
                get_safe_extension=get_safe_extension,
                calculate_file_hash=calculate_file_hash,
                cleanup_file=cleanup_file,
                integrity_error_type=IntegrityError,
            )
        )
        return AppContainer(
            redis_client=redis_client,
            deepseek_provider=deepseek_provider,
            context_agent_router=agent_router,
            context_route_lock_manager=route_lock_manager,
            context_resource_service=resource_service,
            context_service=context_service,
        )
    except Exception:
        try:
            if deepseek_provider is not None:
                await deepseek_provider.aclose()
        finally:
            await close_redis_client(redis_client)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """创建统一容器，并在应用退出时释放其中的外部客户端。"""
    container = await build_container()
    app.state.container = container

    try:
        yield
    finally:
        await container.aclose()
