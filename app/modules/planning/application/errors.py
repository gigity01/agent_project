"""Planning 应用层业务异常定义。

定义 Planning 领域特有的业务错误与控制流异常，
确保与 Tool 映射、HTTP 状态码及 Replan 流程解耦且语义明确。
"""


class PlanningApplicationError(Exception):
    """Planning 领域业务异常基类。

    携带稳定的 HTTP status_code 与机器可读 result_code，
    用于在不直接依赖 FastAPI 或 Agents SDK 的情况下向外层传递明确的错误语义。
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        result_code: str,
    ) -> None:
        """初始化 PlanningApplicationError。

        Args:
            status_code: 建议映射的 HTTP 状态码（如 400, 404, 409, 500, 503）。
            detail: 面向人类的可读错误描述。
            result_code: 稳定的机器可读错误分类码。
        """
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.result_code = result_code


class PlanningRetryRequested(RuntimeError):
    """Planner 控制流异常：前置判断确认本轮应进入 Application 重试语义。

    当规划器在 Gap 分析或执行前判定存在临时缺口或可恢复异常时抛出，
    通知外层编排器将 Plan 转为 retry_pending 状态。
    """

    def __init__(self, reason: str) -> None:
        """初始化 PlanningRetryRequested。

        Args:
            reason: 触发重试的具体原因说明。
        """
        super().__init__(reason)
        self.reason = reason
