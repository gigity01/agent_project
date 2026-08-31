"""可靠消息领域枚举定义。

定义发件箱事件状态与运行时系统支持的核心事件类型。
"""

from enum import Enum


class OutboxEventStatus(str, Enum):
    """事务发件箱（Outbox）事件生命周期状态。

    Attributes:
        PENDING: 待发布状态，等待 OutboxPublisher 轮询扫描并投递。
        PUBLISHED: 已发布状态，表示已成功投递至传输层（如 Redis Streams）。
        DEAD_LETTER: 死信状态，表示重试达到最大次数限制仍未投递成功，需人工介入或告警处理。
    """

    PENDING = "pending"
    PUBLISHED = "published"
    DEAD_LETTER = "dead_letter"


class RuntimeEventType(str, Enum):
    """运行时 Worker 支持的核心事件类型定义。

    Attributes:
        PLAN_WAKEUP: Plan 唤醒事件，触发调度下一个就绪 Task 或补偿操作。
        REPLAN_REQUESTED: 重新规划请求事件，触发 Replan Worker 基于错误事实生成新 Plan revision。
        AGGREGATION_REQUESTED: 聚合请求事件，当全部 Task 成功后触发结果聚合与 Turn 最终完成。
    """

    PLAN_WAKEUP = "runtime.plan_wakeup"
    REPLAN_REQUESTED = "planning.replan_requested"
    AGGREGATION_REQUESTED = "aggregation.requested"
