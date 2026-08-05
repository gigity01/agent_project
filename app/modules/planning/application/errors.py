"""Planning 应用层业务异常。"""


class PlanningApplicationError(Exception):
    """携带稳定 Tool 映射语义，但不依赖 SDK 或 FastAPI。"""

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        result_code: str,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.result_code = result_code
