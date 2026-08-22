"""Clarification 应用层业务异常。"""


class ClarificationApplicationError(RuntimeError):
    """携带安全的 HTTP 映射语义，但不依赖 FastAPI。"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
