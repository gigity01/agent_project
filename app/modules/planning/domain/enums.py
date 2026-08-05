"""Plan 与 Task 的持久化状态枚举。"""

from enum import Enum


class PlanStatus(str, Enum):
    """规划记录状态。"""

    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    UNSUPPORTED = "unsupported"
    NEEDS_CLARIFICATION = "needs_clarification"
    RETRY_PENDING = "retry_pending"
    REPLAN_PENDING = "replan_pending"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class TaskStatus(str, Enum):
    """本阶段接入的 Task 状态。"""

    DRAFT = "draft"
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class PlanningCapabilityCode(str, Enum):
    """当前 Planner 可以创建的领域能力。"""

    PROCESS_DOCUMENT = "process_document"
    BUILD_DOCUMENT_CHUNKS = "build_document_chunks"
    INDEX_DOCUMENT_VECTORS = "index_document_vectors"
