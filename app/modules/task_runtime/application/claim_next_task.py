"""ClaimNextTask 显式 Application 入口。"""

from app.modules.task_runtime.application.dto import ClaimNextTaskInput


class ClaimNextTaskUseCase:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def execute(self, command: ClaimNextTaskInput):
        return self._runtime.claim_next_task(command)
