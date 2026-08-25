"""Clarification 应用层业务异常定义。"""

from __future__ import annotations


class ClarificationApplicationError(RuntimeError):
    """澄清业务应用层异常。

    携带安全的 HTTP 状态码映射语义，供 Presentation 层转换为标准 HTTP 异常，
    确保 Application 层本身不直接依赖 FastAPI / Starlette 框架。

    Attributes:
        status_code: 建议映射的 HTTP 状态码（如 400, 404, 409）。
        detail: 异常描述信息。
    """

    def __init__(self, status_code: int, detail: str) -> None:
        """初始化 ClarificationApplicationError。

        Args:
            status_code: HTTP 状态码。
            detail: 业务异常详情说明。
        """
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
