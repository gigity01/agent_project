"""CompleteTask 显式 Application 入口。"""


class CompleteTaskUseCase:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def execute(self, snapshot, output_json: dict, resource_refs: list[str]):
        return self._runtime.complete_task(
            snapshot,
            output_json,
            resource_refs,
        )
