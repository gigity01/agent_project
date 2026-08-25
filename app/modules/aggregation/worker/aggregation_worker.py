"""消费 aggregation.requested 事件的 Worker 执行器。"""

from __future__ import annotations


class AggregationWorker:
    """Plan 聚合事件处理器。

    作为消息消费端与应用层用例的适配层，接收来自 Redis Stream / Outbox 的
    `aggregation.requested` 事件并委派给 AggregatePlanUseCase 执行。
    """

    def __init__(self, aggregate_plan) -> None:
        """初始化 AggregationWorker。

        Args:
            aggregate_plan: AggregatePlanUseCase 实例或兼容的可调用用例对象。
        """
        self._aggregate_plan = aggregate_plan

    async def handle(self, plan_id: str):
        """处理 Plan 聚合请求。

        Args:
            plan_id: 待聚合的 Plan 唯一标识。

        Returns:
            AggregatePlanUseCase.execute 的执行结果。
        """
        return await self._aggregate_plan.execute(plan_id)
