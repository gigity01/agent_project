"""可靠消息状态。"""

from enum import Enum


class OutboxEventStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    DEAD_LETTER = "dead_letter"


class RuntimeEventType(str, Enum):
    PLAN_WAKEUP = "runtime.plan_wakeup"
    REPLAN_REQUESTED = "planning.replan_requested"
    AGGREGATION_REQUESTED = "aggregation.requested"
