"""Redis Streams 发布与独立 Worker 消费适配器。"""

import json

from redis.exceptions import ResponseError

from app.modules.messaging.application.dto import RuntimeEvent


class RedisStreamPublisher:
    def __init__(self, redis_client, *, stream_name: str = "agent-runtime") -> None:
        self._redis = redis_client
        self._stream_name = stream_name

    async def publish(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        await self._redis.xadd(
            self._stream_name,
            {
                "event_id": event_id,
                "event_type": event_type,
                "payload": json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        )


class RedisStreamWorker:
    """由独立 Worker 进程循环调用，不挂载到 FastAPI lifespan。"""

    def __init__(
        self,
        redis_client,
        *,
        dispatcher,
        stream_name: str = "agent-runtime",
        group_name: str = "agent-runtime-workers",
        consumer_name: str,
        claim_min_idle_milliseconds: int = 60_000,
    ) -> None:
        self._redis = redis_client
        self._dispatcher = dispatcher
        self._stream_name = stream_name
        self._group_name = group_name
        self._consumer_name = consumer_name
        self._claim_min_idle_milliseconds = claim_min_idle_milliseconds

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(
                self._stream_name,
                self._group_name,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run_once(
        self,
        *,
        count: int = 10,
        block_milliseconds: int = 5_000,
    ) -> int:
        """先接管超时消息和恢复本 consumer 未 ACK 消息，再读取新消息。"""

        await self.ensure_group()
        handled = await self._claim_and_dispatch(count=count)
        if handled:
            return handled
        handled = await self._read_and_dispatch(stream_id="0", count=count)
        if handled:
            return handled
        return await self._read_and_dispatch(
            stream_id=">",
            count=count,
            block_milliseconds=block_milliseconds,
        )

    async def _claim_and_dispatch(self, *, count: int) -> int:
        claimed = await self._redis.xautoclaim(
            self._stream_name,
            self._group_name,
            self._consumer_name,
            self._claim_min_idle_milliseconds,
            start_id="0-0",
            count=count,
        )
        messages = claimed[1] if len(claimed) > 1 else []
        return await self._dispatch_messages(messages)

    async def _read_and_dispatch(
        self,
        *,
        stream_id: str,
        count: int,
        block_milliseconds: int | None = None,
    ) -> int:
        streams = await self._redis.xreadgroup(
            self._group_name,
            self._consumer_name,
            {self._stream_name: stream_id},
            count=count,
            block=block_milliseconds,
        )
        handled = 0
        for _, messages in streams:
            handled += await self._dispatch_messages(messages)
        return handled

    async def _dispatch_messages(self, messages) -> int:
        handled = 0
        for message_id, fields in messages:
            event = self._parse_event(fields)
            await self._dispatcher.handle(event)
            await self._redis.xack(
                self._stream_name,
                self._group_name,
                message_id,
            )
            handled += 1
        return handled

    @staticmethod
    def _parse_event(fields: dict) -> RuntimeEvent:
        payload = json.loads(fields["payload"])
        if not isinstance(payload, dict):
            raise ValueError("Runtime Event payload 必须是 JSON Object")
        return RuntimeEvent(
            event_id=fields["event_id"],
            event_type=fields["event_type"],
            payload=payload,
        )
