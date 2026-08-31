"""应用级 Redis 异步客户端工厂与连接管理模块。

职责说明：
- 提供 `create_redis_client` 工厂函数，创建全局共享的 `redis.asyncio.Redis` 客户端。
- 提供 `ping_redis_client` 探测连接可用性（用于应用启动健康检查）。
- 提供 `close_redis_client` 安全关闭客户端连接池。
"""

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis


def create_redis_client(
    url: str,
    *,
    socket_connect_timeout_seconds: int,
    socket_timeout_seconds: int,
) -> Redis:
    """创建由 FastAPI lifespan 与 Worker 生命周期持有并关闭的应用级异步 Redis 客户端。

    参数:
        url: Redis 连接 URI（如 `redis://127.0.0.1:6379/0`）。
        socket_connect_timeout_seconds: TCP 连接建立超时时间（秒）。
        socket_timeout_seconds: Socket 读写操作超时时间（秒）。

    返回:
        Redis: 配置完成的异步 Redis 客户端实例。
    """
    return Redis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=socket_connect_timeout_seconds,
        socket_timeout=socket_timeout_seconds,
    )


async def ping_redis_client(client: Redis) -> bool:
    """发送 PING 命令验证 Redis 服务端连接是否正常。

    兼容 redis-py 8 的同步/异步联合类型标注。

    参数:
        client: Redis 异步客户端。

    返回:
        bool: 服务端正常响应 PONG 时返回 True。
    """
    return await cast(Awaitable[bool], client.ping())


async def close_redis_client(client: Redis) -> None:
    """异步优雅关闭 Redis 客户端底层连接池。

    参数:
        client: 待关闭的 Redis 客户端实例。
    """
    await cast(Awaitable[None], client.aclose())
