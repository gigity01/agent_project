"""消费单个 runtime.plan_wakeup 的薄 Worker 入口。"""

from app.modules.task_runtime.application.runtime import TaskRuntimeService


class RuntimeWorker:
    def __init__(self, runtime: TaskRuntimeService) -> None:
        self._runtime = runtime

    async def handle_plan_wakeup(self, plan_id: str):
        return await self._runtime.execute_next(plan_id)
