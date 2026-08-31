"""基于 Redis 的 Conversation 路由分布式锁隔离与生命周期测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 客户端所有权与共享连接池：
   - ConversationRouteLockManager 仅使用注入的全局 Redis 客户端创建锁，不私自创建连接或调用 aclose()，连接生命周期归属 FastAPI lifespan。
2. 串行化隔离与互斥保护：
   - 同一 Conversation 的路由并发请求通过 Redis 锁（`ctx:{conversation_id}:route:lock`）串行化。
   - 获取锁失败时抛出 `ConversationRouteLockUnavailable` 并阻止进入受保护的业务代码区。
3. 异常安全与可观测性容错：
   - 锁释放异常（如锁超时 expired）记录对应事件并安全上报。
   - EventLogger 写入失败绝不导致已持有的锁悬挂（Strand Lock），确保锁必然被释放。
"""

from __future__ import annotations

import unittest

from redis.exceptions import LockError

from app.modules.context.infrastructure.locking.redis_conversation_lock import (
    ConversationRouteLockManager,
    ConversationRouteLockUnavailable,
)


class _Lock:
    """测试用 Redis 分布式锁替身。"""

    def __init__(
        self,
        *,
        acquired: bool = True,
        release_error: Exception | None = None,
    ) -> None:
        self.acquired = acquired
        self.release_error = release_error
        self.acquire_count = 0
        self.release_count = 0

    async def acquire(self) -> bool:
        self.acquire_count += 1
        return self.acquired

    async def release(self) -> None:
        self.release_count += 1
        if self.release_error is not None:
            raise self.release_error


class _EventLogger:
    """测试用内存事件收集器。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, **fields) -> bool:
        self.events.append({"event": event, **fields})
        return True


class _FailingEventLogger:
    """模拟写入异常的可观测性 Logger 替身。"""

    def write(self, event: str, **fields) -> bool:
        raise OSError("metrics unavailable")


class _RedisClient:
    """测试用 Redis 客户端替身，拦截 lock 调用并记录方法调用次数。"""

    def __init__(self, lock: _Lock) -> None:
        self.returned_lock = lock
        self.calls = []
        self.aclose_count = 0

    def lock(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        return self.returned_lock

    async def aclose(self) -> None:
        self.aclose_count += 1


class ConversationRouteLockManagerTest(
    unittest.IsolatedAsyncioTestCase
):
    """验证 ConversationRouteLockManager 的锁获取/释放、互斥失败、超时以及日志容错。"""

    async def test_uses_injected_client_without_owning_connection(self) -> None:
        """验证锁管理器使用注入的 client 构造锁并在退出上下文时释放，且不擅自关闭 Redis 连接池。"""
        lock = _Lock()
        client = _RedisClient(lock)
        event_logger = _EventLogger()
        manager = ConversationRouteLockManager(
            client,
            lock_timeout_seconds=30,
            blocking_timeout_seconds=2,
            event_logger=event_logger,
        )

        async with manager.hold("conversation-1"):
            self.assertEqual(lock.acquire_count, 1)

        self.assertEqual(lock.release_count, 1)
        self.assertEqual(client.aclose_count, 0)
        self.assertFalse(hasattr(manager, "aclose"))
        self.assertFalse(hasattr(manager, "from_url"))
        self.assertEqual(
            client.calls,
            [
                (
                    "ctx:{conversation-1}:route:lock",
                    {
                        "timeout": 30,
                        "blocking_timeout": 2,
                        "thread_local": False,
                    },
                )
            ],
        )
        self.assertEqual(
            [event["event"] for event in event_logger.events],
            ["context_route_lock_acquired", "context_route_lock_released"],
        )
        self.assertIn(
            "context_route_lock_wait_duration",
            event_logger.events[0],
        )
        self.assertIn(
            "context_route_lock_hold_duration",
            event_logger.events[1],
        )

    async def test_unavailable_lock_fails_without_entering_scope(self) -> None:
        """验证加锁失败时直接抛出 ConversationRouteLockUnavailable，不进入业务作用域。"""
        client = _RedisClient(_Lock(acquired=False))
        event_logger = _EventLogger()
        manager = ConversationRouteLockManager(
            client,
            lock_timeout_seconds=30,
            blocking_timeout_seconds=2,
            event_logger=event_logger,
        )

        with self.assertRaisesRegex(
            ConversationRouteLockUnavailable,
            "conversation-1",
        ):
            async with manager.hold("conversation-1"):
                self.fail("锁获取失败时不应进入受保护作用域")
        self.assertEqual(
            event_logger.events[0]["event"],
            "context_route_lock_unavailable",
        )

    async def test_expired_lock_records_hold_duration(self) -> None:
        """验证锁在持有期间超时后释放失败时抛出异常并准确记录持有时间指标。"""
        event_logger = _EventLogger()
        manager = ConversationRouteLockManager(
            _RedisClient(_Lock(release_error=LockError("expired"))),
            lock_timeout_seconds=30,
            blocking_timeout_seconds=2,
            event_logger=event_logger,
        )

        with self.assertRaisesRegex(
            ConversationRouteLockUnavailable,
            "expired",
        ):
            async with manager.hold("conversation-1"):
                pass

        event = event_logger.events[-1]
        self.assertEqual(event["event"], "context_route_lock_expired")
        self.assertEqual(event["context_route_lock_expired_count"], 1)
        self.assertIn("context_route_lock_hold_duration", event)

    async def test_observability_failure_never_strands_acquired_lock(
        self,
    ) -> None:
        """验证即使 EventLogger 发生故障抛出异常，获取成功的锁仍然必定在 finally 中被释放，杜绝死锁。"""
        lock = _Lock()
        manager = ConversationRouteLockManager(
            _RedisClient(lock),
            lock_timeout_seconds=30,
            blocking_timeout_seconds=2,
            event_logger=_FailingEventLogger(),
        )

        async with manager.hold("conversation-1"):
            self.assertEqual(lock.acquire_count, 1)

        self.assertEqual(lock.release_count, 1)


if __name__ == "__main__":
    unittest.main()
