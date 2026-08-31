"""Task Runtime 显式错误分类与异常定义。

定义 Task 执行过程中的业务错误与异常模型，支持区分重试（retryable）与阻塞（blocked）。
"""


class TaskExecutionError(Exception):
    """Task 执行异常基类。

    携带结构化的错误分类码、可重试性标记以及阻塞标记。
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        retryable: bool,
        blocked: bool = False,
    ) -> None:
        """初始化 TaskExecutionError。

        Args:
            error_code: 稳定的错误分类码。
            message: 面向人类的错误详细信息。
            retryable: 是否属于可自动重试的瞬态错误（若为 True 且尝试次数未耗尽，则进入 RETRY_WAIT）。
            blocked: 是否属于业务前置条件不满足导致的阻塞（若为 True，则直接将 Task 标记为 BLOCKED 并触发 Replan）。
        """
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.blocked = blocked
