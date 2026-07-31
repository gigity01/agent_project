"""FastAPI 应用生命周期与对象装配。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.context_agent import ContextAgentRouter
from app.agents.deepseek_provider import DeepSeekModelProvider
from app.app_config.settings import (
    CONTEXT_RESOURCE_QUEUE_MAX_SIZE,
    CONTEXT_ROUTE_LOCK_BLOCKING_TIMEOUT_SECONDS,
    CONTEXT_ROUTE_LOCK_TIMEOUT_SECONDS,
    DEEPSEEK_API_KEY,
    REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
    REDIS_SOCKET_TIMEOUT_SECONDS,
    REDIS_URL,
)
from app.bootstrap.container import AppContainer
from app.integrations.context_resource_queue import (
    ContextResourceQueueRepository,
)
from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
)
from app.integrations.redis_client import (
    close_redis_client,
    create_redis_client,
    ping_redis_client,
)
from app.services.context_resource_service import ContextResourceService
from app.services.context_service import ContextService


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
        resource_service = ContextResourceService(
            queue_repository=queue_repository,
        )
        deepseek_provider = (
            DeepSeekModelProvider.create()
            if DEEPSEEK_API_KEY is not None
            else None
        )
        agent_router = (
            ContextAgentRouter(deepseek_provider)
            if deepseek_provider is not None
            else None
        )
        context_service = ContextService(
            agent_router=agent_router,
            route_lock_manager=route_lock_manager,
            resource_service=resource_service,
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
