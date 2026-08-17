"""Redis Conversation 路由锁的客户端所有权测试。"""

from __future__ import annotations

import unittest

from redis.exceptions import LockError

from app.modules.context.infrastructure.locking.redis_conversation_lock import (
    ConversationRouteLockManager,
    ConversationRouteLockUnavailable,
)


class _Lock:
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
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, **fields) -> bool:
        self.events.append({"event": event, **fields})
        return True


class _FailingEventLogger:
    def write(self, event: str, **fields) -> bool:
        raise OSError("metrics unavailable")


class _RedisClient:
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
    async def test_uses_injected_client_without_owning_connection(self) -> None:
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
