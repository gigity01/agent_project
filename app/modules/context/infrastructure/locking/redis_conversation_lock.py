"""基于 Redis 的 Conversation 级 Context 路由短锁基础设施实现。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic_ns
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import LockError

from app.modules.context.application.errors import (
    ConversationLockUnavailable,
)


ConversationRouteLockUnavailable = ConversationLockUnavailable


class ConversationRouteLockManager:
    """使用应用级共享 Redis 客户端串行化 Context 路由的锁管理器。

    设计原则：
    - 粒度：按 conversation_id 隔离（Key: `ctx:{conversation_id}:route:lock`）。
    - 短锁策略：仅在执行路由判定与更新上下文短事务期间持有，避免长期占用。
    - 超时控制：配置独立的 lock_timeout（锁最大持有时间）与 blocking_timeout（等待获取锁最大等待时间）。
    """

    def __init__(
        self,
        client: Redis,
        *,
        lock_timeout_seconds: int,
        blocking_timeout_seconds: int,
        event_logger: Any | None = None,
    ) -> None:
        """初始化 ConversationRouteLockManager。

        Args:
            client: Redis 异步客户端。
            lock_timeout_seconds: 锁自动过期超时时间（秒）。
            blocking_timeout_seconds: 等待锁的最大阻塞超时时间（秒）。
            event_logger: 可观测性事件日志记录器。

        Raises:
            ValueError: 超时参数不合法时抛出。
        """
        if lock_timeout_seconds < 1:
            raise ValueError("Conversation route lock timeout must be positive")
        if blocking_timeout_seconds < 0:
            raise ValueError(
                "Conversation route blocking timeout cannot be negative"
            )
        self._client = client
        self._lock_timeout_seconds = lock_timeout_seconds
        self._blocking_timeout_seconds = blocking_timeout_seconds
        self._event_logger = event_logger

    @asynccontextmanager
    async def hold(self, conversation_id: str) -> AsyncIterator[None]:
        """获取指定会话的分布式短锁异步上下文管理器。

        Args:
            conversation_id: 会话唯一标识。

        Yields:
            None: 成功进入临界区。

        Raises:
            ConversationRouteLockUnavailable: 锁获取超时或释放时发现锁已超时过期。
        """
        wait_started_at = monotonic_ns()
        lock = self._client.lock(
            f"ctx:{{{conversation_id}}}:route:lock",
            timeout=self._lock_timeout_seconds,
            blocking_timeout=self._blocking_timeout_seconds,
            thread_local=False,
        )
        acquired = await lock.acquire()
        wait_duration_ms = self._elapsed_ms(wait_started_at)
        if not acquired:
            self._observe(
                "context_route_lock_unavailable",
                level="warning",
                conversation_id=conversation_id,
                context_route_lock_wait_duration=wait_duration_ms,
                context_route_lock_expired_count=0,
                duration_unit="milliseconds",
            )
            raise ConversationRouteLockUnavailable(
                f"Conversation route lock unavailable: {conversation_id}"
            )

        hold_started_at = monotonic_ns()
        self._observe(
            "context_route_lock_acquired",
            conversation_id=conversation_id,
            context_route_lock_wait_duration=wait_duration_ms,
            context_route_lock_expired_count=0,
            duration_unit="milliseconds",
        )
        try:
            yield
        finally:
            try:
                await lock.release()
            except LockError as exc:
                self._observe(
                    "context_route_lock_expired",
                    level="warning",
                    conversation_id=conversation_id,
                    context_route_lock_wait_duration=wait_duration_ms,
                    context_route_lock_hold_duration=self._elapsed_ms(
                        hold_started_at
                    ),
                    context_route_lock_expired_count=1,
                    duration_unit="milliseconds",
                )
                raise ConversationRouteLockUnavailable(
                    f"Conversation route lock expired: {conversation_id}"
                ) from exc
            self._observe(
                "context_route_lock_released",
                conversation_id=conversation_id,
                context_route_lock_wait_duration=wait_duration_ms,
                context_route_lock_hold_duration=self._elapsed_ms(
                    hold_started_at
                ),
                context_route_lock_expired_count=0,
                duration_unit="milliseconds",
            )

    @staticmethod
    def _elapsed_ms(started_at: int) -> float:
        """计算自 started_at（纳秒）以来的毫秒数。"""
        return round((monotonic_ns() - started_at) / 1_000_000, 3)

    def _observe(self, event: str, **fields: Any) -> None:
        """记录结构化观察事件。"""
        if self._event_logger is None:
            return
        try:
            self._event_logger.write(event, **fields)
        except Exception:
            # 尽力记录日志，禁止因日志记录异常影响业务流程
            return
