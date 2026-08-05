"""ExecuteTask 三段式 Application 入口。"""


class ExecuteTaskUseCase:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    async def execute(self, plan_id: str):
        return await self._runtime.execute_next(plan_id)
