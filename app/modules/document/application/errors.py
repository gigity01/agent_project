"""文档应用层异常。"""


class DocumentApplicationError(Exception):
    """携带 HTTP 可映射状态码，但不依赖 FastAPI。"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
