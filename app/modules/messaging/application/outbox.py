"""可在独立 Worker 进程循环调用的发件箱（Outbox）发布器。

基于 Transactional Outbox 模式，在短事务内批量拉取未发布的事件，
通过 MessagePublisherPort 发布至底层消息队列（如 Redis Streams），
并根据发布结果在独立短事务中更新状态为 PUBLISHED 或递增重试次数（达到上限后转为 DEAD_LETTER）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from app.modules.messaging.application.ports import MessagePublisherPort
from app.modules.messaging.domain.enums import OutboxEventStatus


@dataclass(frozen=True)
class _EventSnapshot:
    """发件箱事件内存快照，用于跨异步边界传递数据。

    Attributes:
        event_id: 事件全局唯一标识符。
        event_type: 事件类型。
        payload: 事件载荷字典。
    """

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
            uow_factory: 工作单元工厂函数，每次调用产生独立短事务的 UoW。
            publisher: 消息发布端端口实例（如 RedisStreamPublisher）。
            max_attempts: 最大投递重试次数，达到后标记为死信。默认值为 10。
        """
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._max_attempts = max_attempts

    async def publish_batch(self, limit: int = 100) -> int:
        """批量加载并发布待发送事件。

        在独立线程中通过短事务加载待发布快照，逐条发布到传输层；
        发布成功后在短事务中标记为 PUBLISHED，失败则在短事务中记录重试或标记死信。

        Args:
            limit: 单批最大处理条数，默认 100。

        Returns:
            int: 本批次成功发布的事件数量。
        """
        # 1. 事务内加锁加载待发布事件快照
        snapshots = await asyncio.to_thread(self._load_batch, limit)
        published = 0

        # 2. 逐条发布并根据结果回写状态
        for event in snapshots:
            try:
                await self._publisher.publish(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    payload=event.payload,
                )
            except Exception:
                # 发布失败：记录重试次数或标记死信
                await asyncio.to_thread(self._mark_failed, event.event_id)
                continue

            # 发布成功：标记已发布
            await asyncio.to_thread(self._mark_published, event.event_id)
            published += 1
        return published

    def _load_batch(self, limit: int) -> list[_EventSnapshot]:
        """在独立短事务中行锁查询待投递事件快照。

        使用 SKIP LOCKED 防止多 Worker 进程并发扫描时的锁冲突。

        Args:
            limit: 最大查询条数。

        Returns:
            list[_EventSnapshot]: 待发布的事件快照列表。
        """
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
        """在独立短事务中标记事件已成功发布。

        Args:
            event_id: 成功发布的事件唯一标识。
        """
        with self._uow_factory() as uow:
            event = uow.outbox.get_by_id_for_update(event_id)
            if event is None or event.status != OutboxEventStatus.PENDING.value:
                return
            event.status = OutboxEventStatus.PUBLISHED.value
            event.published_at = datetime.now()
            uow.commit()

    def _mark_failed(self, event_id: str) -> None:
        """在独立短事务中记录发布失败并递增重试次数；达到上限则转入死信状态。

        Args:
            event_id: 发布失败的事件唯一标识。
        """
        with self._uow_factory() as uow:
            event = uow.outbox.get_by_id_for_update(event_id)
            if event is None or event.status != OutboxEventStatus.PENDING.value:
                return
            event.attempts += 1
            if event.attempts >= self._max_attempts:
                event.status = OutboxEventStatus.DEAD_LETTER.value
            uow.commit()
