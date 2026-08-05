"""可在独立进程循环调用的 Outbox Publisher。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from app.modules.messaging.application.ports import MessagePublisherPort
from app.modules.messaging.domain.enums import OutboxEventStatus


@dataclass(frozen=True)
class _EventSnapshot:
    event_id: str
    event_type: str
    payload: dict


class OutboxPublisher:
    def __init__(
        self,
        *,
        uow_factory,
        publisher: MessagePublisherPort,
        max_attempts: int = 10,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._max_attempts = max_attempts

    async def publish_batch(self, limit: int = 100) -> int:
        snapshots = await asyncio.to_thread(self._load_batch, limit)
        published = 0
        for event in snapshots:
            try:
                await self._publisher.publish(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    payload=event.payload,
                )
            except Exception:
                await asyncio.to_thread(self._mark_failed, event.event_id)
                continue
            await asyncio.to_thread(self._mark_published, event.event_id)
            published += 1
        return published

    def _load_batch(self, limit: int) -> list[_EventSnapshot]:
        with self._uow_factory() as uow:
            events = uow.outbox.list_available_for_update(
                status=OutboxEventStatus.PENDING.value,
                now=datetime.now(),
                limit=limit,
            )
            return [
                _EventSnapshot(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    payload=dict(event.payload_json),
                )
                for event in events
            ]

    def _mark_published(self, event_id: str) -> None:
        with self._uow_factory() as uow:
            event = uow.outbox.get_by_id_for_update(event_id)
            if event is None or event.status != OutboxEventStatus.PENDING.value:
                return
            event.status = OutboxEventStatus.PUBLISHED.value
            event.published_at = datetime.now()
            uow.commit()

    def _mark_failed(self, event_id: str) -> None:
        with self._uow_factory() as uow:
            event = uow.outbox.get_by_id_for_update(event_id)
            if event is None or event.status != OutboxEventStatus.PENDING.value:
                return
            event.attempts += 1
            if event.attempts >= self._max_attempts:
                event.status = OutboxEventStatus.DEAD_LETTER.value
            uow.commit()
