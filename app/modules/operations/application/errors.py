"""Operations 查询错误。"""


class OperationsQueryError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.result_code = "operations_query_rejected"
