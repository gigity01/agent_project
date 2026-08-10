"""FailTask 显式 Application 入口。"""


class FailTaskUseCase:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    async def execute(self, snapshot, error):
        return await self._runtime.fail_task(snapshot, error)
