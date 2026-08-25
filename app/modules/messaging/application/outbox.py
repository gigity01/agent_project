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
    """可靠事件发件箱（Transactional Outbox）发布器。

    在独立 Worker 进程中循环拉取数据库中待发布的事件，
    将其投递至 Redis Stream，并在成功后原子更新状态为 PUBLISHED；
    发布失败时递增尝试次数，超过最大尝试上限后转入 DEAD_LETTER 死信状态。
    """

    def __init__(
        self,
        *,
        uow_factory,
        publisher: MessagePublisherPort,
        max_attempts: int = 10,
    ) -> None:
        """初始化 Outbox 发布器。

        Args:
            uow_factory: 工作单元工厂。
            publisher: 消息发布端（如 RedisStreamPublisher）。
            max_attempts: 最大投递重试次数，达到后标记为死信。
        """
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._max_attempts = max_attempts

    async def publish_batch(self, limit: int = 100) -> int:
        """批量加载并发布待发送事件。

        Args:
            limit: 单批最大处理条数。

        Returns:
            int: 成功发布的事件数量。
        """
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
        """在独立短事务中行锁查询待投递事件快照。"""
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
        """标记事件已成功发布。"""
        with self._uow_factory() as uow:
            event = uow.outbox.get_by_id_for_update(event_id)
            if event is None or event.status != OutboxEventStatus.PENDING.value:
                return
            event.status = OutboxEventStatus.PUBLISHED.value
            event.published_at = datetime.now()
            uow.commit()

    def _mark_failed(self, event_id: str) -> None:
        """记录发布失败并递增重试次数；达到上限则转入死信状态。"""
        with self._uow_factory() as uow:
            event = uow.outbox.get_by_id_for_update(event_id)
            if event is None or event.status != OutboxEventStatus.PENDING.value:
                return
            event.attempts += 1
            if event.attempts >= self._max_attempts:
                event.status = OutboxEventStatus.DEAD_LETTER.value
            uow.commit()
