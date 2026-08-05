"""FailTask 显式 Application 入口。"""


class FailTaskUseCase:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def execute(self, snapshot, error):
        return self._runtime.fail_task(snapshot, error)
