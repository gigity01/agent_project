"""Context 应用层业务异常定义。"""

from __future__ import annotations


class ContextApplicationError(RuntimeError):
    """Context 模块应用层异常基类，可由 Presentation 层转换为相应的 HTTP 协议状态码。"""


class ContextRoutingError(ContextApplicationError):
    """Context Router 调用失败或返回结果非法时抛出的路由异常（通常映射为 502）。"""


class ContextTurnNotFoundError(ContextApplicationError):
    """指定的 Context Turn 不存在时抛出（通常映射为 404）。"""


class ContextConflictError(ContextApplicationError):
    """Context 生命周期状态不一致或与当前操作冲突时抛出（通常映射为 409）。"""


class ContextValidationError(ContextApplicationError):
    """应用命令违反 Context 业务输入约束时抛出（通常映射为 400）。"""


class ConversationLockUnavailable(ContextApplicationError):
    """会话级 Redis 串行锁在等待窗口内争抢超时时抛出（通常映射为 409）。"""


class ContextQueryError(ContextApplicationError):
    """Context 只读查询的安全外部异常。

    Attributes:
        status_code: HTTP 状态码（如 404, 400）。
        detail: 异常详情说明。
        result_code: 安全的结构化返回码。
    """

    def __init__(self, status_code: int, detail: str) -> None:
        """初始化 ContextQueryError。

        Args:
            status_code: HTTP 状态码。
            detail: 异常描述信息。
        """
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.result_code = (
            "context_resource_not_found"
            if status_code == 404
            else "context_query_rejected"
        )
