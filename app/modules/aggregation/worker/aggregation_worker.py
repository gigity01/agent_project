"""消费 aggregation.requested 的薄 Worker。"""


class AggregationWorker:
    def __init__(self, aggregate_plan) -> None:
        self._aggregate_plan = aggregate_plan

    async def handle(self, plan_id: str):
        return await self._aggregate_plan.execute(plan_id)
