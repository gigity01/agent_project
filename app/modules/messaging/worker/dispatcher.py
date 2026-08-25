"""按最少事件集合调度业务 Worker，并用 Inbox 抑制已完成重复消息。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from app.modules.messaging.application.dto import RuntimeEvent
from app.modules.messaging.domain.enums import RuntimeEventType
from app.modules.planning.application.replan import ReplanRequested

class RuntimeEventDispatcher:
    """Runtime 事件分派器。

    根据事件类型将消息路由至对应业务执行器，并基于 Inbox 模式实现幂等去重：
    - REPLAN_REQUESTED: 触发重新规划（Replan）。
    - PLAN_WAKEUP: 唤醒 Plan 下一个就绪任务或补偿执行。
    - AGGREGATION_REQUESTED: 任务全数成功后的确定性结果聚合与 Turn 完成。
    """

    CONSUMER_NAME = "runtime.dispatcher"

    def __init__(
        self,
        *,
        uow_factory,
        inbox_event_factory,
        runtime,
        replan,
        aggregate_plan,
    ) -> None:
        self._uow_factory = uow_factory
        self._inbox_event_factory = inbox_event_factory
        self._runtime = runtime
        self._replan = replan
        self._aggregate_plan = aggregate_plan

    async def handle(self, event: RuntimeEvent):
        """处理分派接收到的 Runtime 事件。"""
        # 1. 重新规划请求事件
        if event.event_type == RuntimeEventType.REPLAN_REQUESTED.value:
            if self._replan is None:
                raise RuntimeError("Replan Worker 未配置")
            return await self._replan.execute(
                ReplanRequested(event_id=event.event_id, **event.payload)
            )

        # 2. Plan 唤醒与下一任务执行事件
        if event.event_type == RuntimeEventType.PLAN_WAKEUP.value:
            return await self._runtime.execute_next(
                event.payload["plan_id"],
                event_id=event.event_id,
                compensation_execution_id=event.payload.get("execution_id"),
                compensation_operation_id=event.payload.get("operation_id"),
            )

        # 3. 聚合请求事件（需通过 Inbox 幂等校验）
        if await asyncio.to_thread(self._already_processed, event.event_id):
            return None
        if event.event_type == RuntimeEventType.AGGREGATION_REQUESTED.value:
            result = await self._aggregate_plan.execute(event.payload["plan_id"])
        else:
            raise ValueError(f"未知 Runtime Event: {event.event_type}")
        await asyncio.to_thread(self._record_processed, event.event_id)
        return result

    def _already_processed(self, event_id: str) -> bool:
        """检查指定事件是否已在当前消费者的 Inbox 中记录。"""
        with self._uow_factory() as uow:
            return uow.inbox.exists(self.CONSUMER_NAME, event_id)

    def _record_processed(self, event_id: str) -> None:
        """在当前消费者的 Inbox 中记录已处理事件，防止重复消费。"""
        with self._uow_factory() as uow:
            if uow.inbox.exists(self.CONSUMER_NAME, event_id):
                return
            uow.inbox.add(
                self._inbox_event_factory(
                    inbox_id=f"inbox_{uuid4().hex}",
                    consumer_name=self.CONSUMER_NAME,
                    event_id=event_id,
                    processed_at=datetime.now(),
                )
            )
            uow.commit()
