"""应用级 Redis 异步客户端工厂。"""

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis


def create_redis_client(
    url: str,
    *,
    socket_connect_timeout_seconds: int,
    socket_timeout_seconds: int,
) -> Redis:
    """创建由 FastAPI lifespan 持有并关闭的 Redis 客户端。"""
    return Redis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=socket_connect_timeout_seconds,
        socket_timeout=socket_timeout_seconds,
    )


async def ping_redis_client(client: Redis) -> bool:
    """验证 Redis 连接，并兼容 redis-py 8 的同步/异步联合类型标注。"""
    return await cast(Awaitable[bool], client.ping())


async def close_redis_client(client: Redis) -> None:
    """关闭 Redis 客户端，并隔离 redis-py 8 不准确的异步返回类型。"""
    await cast(Awaitable[None], client.aclose())
