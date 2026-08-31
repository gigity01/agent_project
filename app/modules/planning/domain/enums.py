"""Plan 与 Task 的持久化状态枚举。

定义规划生命周期中的核心状态枚举，包括 Plan 的整体规划状态、
单个 Task 的执行流转状态以及当前系统支持的领域能力编码。
"""

from enum import Enum


class PlanStatus(str, Enum):
    """规划记录（Plan）的生命周期状态枚举。

    状态流转说明：
    - PLANNING: 初始状态，Planner 正在生成或修订任务拓扑。
    - READY: Plan 及其关联 Tasks 已完成 DAG 校验并成功发布，等待 Runtime Worker 领取。
    - RUNNING: 至少有一个关联 Task 正在执行中。
    - COMPLETED: Plan 下的所有 Tasks 均已成功执行，等待或已完成结果聚合。
    - UNSUPPORTED: Planner 判定当前请求无法由系统现有能力支持。
    - NEEDS_CLARIFICATION: Planner 判定请求存在歧义或缺失必要参数，等待用户澄清。
    - RETRY_PENDING: Planner 规划过程出现偶发异常或中断，等待系统自动重试。
    - REPLAN_PENDING: 任务执行失败或受阻，等待触发下一版本 Replan。
    - FAILED: Plan 达到最大重试/修订次数上限，最终失败。
    - CANCELLED: Plan 被主动取消。
    - SUPERSEDED: 新版本 Plan revision 发布后，旧版本 Plan 被标记为已被取代。
    """

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
    """单个任务（Task）的执行与生命周期状态枚举。

    状态流转说明：
    - DRAFT: Planner 正在草拟阶段创建的任务。
    - PENDING: Plan 正式发布后，任务就绪等待前置依赖满足并被 Claim。
    - RUNNING: 任务已被 Worker Claim 并正在执行。
    - RETRY_WAIT: 任务执行发生可重试错误，处于退避等待状态。
    - SUCCEEDED: 任务执行成功且结果已持久化。
    - BLOCKED: 任务由于业务前置条件不满足被拒绝，触发 Replan。
    - FAILED: 任务尝试次数耗尽或发生不可重试的致命错误。
    - CANCELLED: 任务被主动取消。
    - SUPERSEDED: 新 Plan revision 生成后，旧版本未完成的任务被废弃。
    """

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
    """当前 Planner 具备且允许创建的领域能力枚举。"""

    PROCESS_DOCUMENT = "process_document"
    BUILD_DOCUMENT_CHUNKS = "build_document_chunks"
    INDEX_DOCUMENT_VECTORS = "index_document_vectors"
