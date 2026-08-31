"""文档应用层业务异常定义。

定义与 HTTP 状态码解耦但携带映射状态码的应用层异常类。
"""


class DocumentApplicationError(Exception):
    """文档应用层通用业务异常基类。

    携带 HTTP 映射状态码（status_code）和错误明细（detail），
    使应用层能够表达标准业务错误而不直接依赖 FastAPI 等具体 Web 框架。

    Attributes:
        status_code: 建议的 HTTP 响应状态码（如 400, 404, 409 等）。
        detail: 针对客户端或调用方的详细错误提示信息。
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
