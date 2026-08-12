"""Redis Streams Worker 的离线消费与 ACK 行为。"""

from __future__ import annotations

import json
import unittest

from app.modules.messaging.infrastructure.redis_streams import RedisStreamWorker


class _FakeRedis:
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
    def __init__(self, *, fail: bool = False) -> None:
        self.events = []
        self._fail = fail

    async def handle(self, event):
        self.events.append(event)
        if self._fail:
            raise RuntimeError("dispatch failed")


class RedisStreamWorkerTest(unittest.IsolatedAsyncioTestCase):
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
