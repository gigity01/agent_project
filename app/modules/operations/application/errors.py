"""Operations 模块异常定义。

定义日志查询过程中发生的业务与参数校验异常。
"""


class OperationsQueryError(RuntimeError):
    """Operations 日志查询异常。

    用于表达参数不合法（如 cursor 无效、limit 非法）或底层存储不可用等业务拒绝与错误场景。

    Attributes:
        status_code: 建议映射的 HTTP 状态码（如 400, 503 等）。
        detail: 异常详情说明。
        result_code: 结构化错误代码（默认为 "operations_query_rejected"）。
    """

    def __init__(self, status_code: int, detail: str) -> None:
        """初始化查询异常。

        Args:
            status_code: 错误状态码。
            detail: 错误详细描述。
        """
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.result_code = "operations_query_rejected"
