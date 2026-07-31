"""Context Application 层错误。"""


class ContextApplicationError(RuntimeError):
    """可由 Presentation 映射为外部协议错误的应用异常。"""


class ContextRoutingError(ContextApplicationError):
    """Context Router 调用或返回结果不可用。"""


class ContextTurnNotFoundError(ContextApplicationError):
    """指定 Context Turn 不存在。"""


class ContextConflictError(ContextApplicationError):
    """Context 状态或归属与当前操作冲突。"""


class ContextValidationError(ContextApplicationError):
    """应用命令违反 Context 业务输入约束。"""


class ConversationLockUnavailable(ContextApplicationError):
    """Conversation 级串行锁在等待窗口内不可用。"""
