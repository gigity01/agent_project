"""Task Runtime 领域状态枚举。

定义任务单次执行尝试（TaskExecution）的生命周期状态，
以及补偿被永久冻结时的原因分类枚举。
"""

from enum import Enum


class TaskExecutionStatus(str, Enum):
    """TaskExecution 单次执行尝试的生命周期状态枚举。

    状态流转说明：
    - RUNNING: 任务已被 Claim，Executor 正在事务外执行。
    - COMPENSATION_REQUIRED: 执行失败或超时租约过期，需执行确定性补偿以清理副作用。
    - COMPENSATION_LOCKED: 自动补偿尝试次数耗尽或发生系统致命错误，补偿生命周期被冻结并保留 ownership，禁止新 attempt 接管。
    - COMPENSATED: 副作用已被成功补偿清理，释放 ownership 并进入 retry_wait 或 replan。
    - SUCCEEDED: 任务执行成功，产物与结果已落盘。
    - FAILED: 无副作用任务直接失败。
    """

    RUNNING = "running"
    COMPENSATION_REQUIRED = "compensation_required"
    COMPENSATION_LOCKED = "compensation_locked"
    COMPENSATED = "compensated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CompensationLockReason(str, Enum):
    """补偿生命周期被锁定（COMPENSATION_LOCKED）的具体原因枚举。"""

    RETRY_EXHAUSTED = "retry_exhausted"
    SYSTEM_FAILURE = "system_failure"
    UNKNOWN = "unknown"
