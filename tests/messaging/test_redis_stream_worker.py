"""Redis Streams Worker 消费者组消费、死信抢占（Autoclaim）与 ACK 机制测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 消费组与死信抢占（PEL Claim）：
   - Worker 优先通过 `xautoclaim` 抢占 PEL 中超时的待处理消息，实现崩溃实例未完成消息的无缝接管，再通过 `xreadgroup` 读取新消息。
2. 业务处理成功后后置 ACK：
   - 消息只有在业务分派与持久化完全成功后才调用 `xack`；业务处理失败时不 ACK，保留在 pending 列表中供后续重试或由集群其他实例接管。
"""

from __future__ import annotations

import json
import unittest

from app.modules.messaging.infrastructure.redis_streams import RedisStreamWorker


class _FakeRedis:
    """测试用 Redis Streams 客户端替身，模拟 xgroup_create, xautoclaim, xreadgroup 与 xack。"""
    def __init__(self, messages, *, claimed_messages=None) -> None:
        self._messages = list(messages)
        self._claimed_messages = list(claimed_messages or [])
        self.acks: list[str] = []

    async def xgroup_create(self, *args, **kwargs):
        return True

    async def xautoclaim(self, *args, **kwargs):
        messages, self._claimed_messages = self._claimed_messages, []
        return ["0-0", messages]

    async def xreadgroup(self, *args, **kwargs):
        stream_id = next(iter(args[2].values()))
        if stream_id == "0":
            return []
        messages, self._messages = self._messages, []
        return [("agent-runtime", messages)] if messages else []

    async def xack(self, stream_name, group_name, message_id):
        self.acks.append(message_id)


class _Dispatcher:
    """测试用事件分派器替身。"""
    def __init__(self, *, fail: bool = False) -> None:
        self.events = []
        self._fail = fail

    async def handle(self, event):
        self.events.append(event)
        if self._fail:
            raise RuntimeError("dispatch failed")


class RedisStreamWorkerTest(unittest.IsolatedAsyncioTestCase):
    """验证 RedisStreamWorker 的超时接管、新消息消费与错误不 ACK 行为。"""
    async def test_claims_timed_out_message_before_reading_new_one(self) -> None:
        redis = _FakeRedis(
            [],
            claimed_messages=[
                (
                    "0-1",
                    {
                        "event_id": "event-0",
                        "event_type": "runtime.plan_wakeup",
                        "payload": json.dumps({"plan_id": "plan-0"}),
                    },
                )
            ],
        )
        dispatcher = _Dispatcher()
        worker = RedisStreamWorker(
            redis,
            dispatcher=dispatcher,
            consumer_name="worker-2",
        )

        handled = await worker.run_once(block_milliseconds=0)

        self.assertEqual(handled, 1)
        self.assertEqual(dispatcher.events[0].event_id, "event-0")
        self.assertEqual(redis.acks, ["0-1"])

    async def test_dispatches_and_acknowledges_successful_message(self) -> None:
        redis = _FakeRedis(
            [
                (
                    "1-0",
                    {
                        "event_id": "event-1",
                        "event_type": "runtime.plan_wakeup",
                        "payload": json.dumps({"plan_id": "plan-1"}),
                    },
                )
            ]
        )
        dispatcher = _Dispatcher()
        worker = RedisStreamWorker(
            redis,
            dispatcher=dispatcher,
            consumer_name="worker-1",
        )

        handled = await worker.run_once(block_milliseconds=0)

        self.assertEqual(handled, 1)
        self.assertEqual(dispatcher.events[0].event_id, "event-1")
        self.assertEqual(redis.acks, ["1-0"])

    async def test_does_not_ack_failed_dispatch(self) -> None:
        redis = _FakeRedis(
            [
                (
                    "2-0",
                    {
                        "event_id": "event-2",
                        "event_type": "aggregation.requested",
                        "payload": json.dumps({"plan_id": "plan-2"}),
                    },
                )
            ]
        )
        worker = RedisStreamWorker(
            redis,
            dispatcher=_Dispatcher(fail=True),
            consumer_name="worker-1",
        )

        with self.assertRaisesRegex(RuntimeError, "dispatch failed"):
            await worker.run_once(block_milliseconds=0)

        self.assertEqual(redis.acks, [])


if __name__ == "__main__":
    unittest.main()
