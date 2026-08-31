"""Context 领域枚举定义。"""

from __future__ import annotations

from enum import Enum


class ContextSelectionMode(str, Enum):
    """Planner 历史上下文读取集合的派生规模模式。

    - NO_CONTEXT: 历史读取集合为空；最终链归属由下游 Attribution 决定。
    - SINGLE_CONTEXT: 关联单条已有历史链。
    - MULTI_CONTEXT: 同时关联多条已有历史链。
    """

    NO_CONTEXT = "no_context"
    SINGLE_CONTEXT = "single_context"
    MULTI_CONTEXT = "multi_context"


class ContextTurnStatus(str, Enum):
    """ConversationTurn 生命周期状态枚举。

    状态流转：
    - ROUTING: 正在执行 Context 路由判定。
    - CONTEXT_READY: 上下文已确定并持久化，等待/正在移交 Planner。
    - PROCESSING: Planner 正在规划或 Task Runtime 正在异步执行 Task DAG。
    - COMPLETED: 下游任务全部成功，聚合完成，已回写助手回答并刷新资源。
    - FAILED: 规划或任务执行失败终态。
    - NEEDS_CLARIFICATION: Planner 发起澄清提问，正在等待用户补充输入。
    """

    ROUTING = "routing"
    CONTEXT_READY = "context_ready"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_CLARIFICATION = "needs_clarification"


class ContextResourceAction(str, Enum):
    """上下文链资源生命周期事件动作类型。

    - SEEN: 资源在当前链中被首次引用。
    - REFRESHED: 资源被再次使用，在热队列中刷新其最近活跃时间。
    - REMOVED: 资源被从链的当前上下文中显式移除。
    - INVALIDATED: 资源已失效（如文档被删除或替换）。
    """

    SEEN = "seen"
    REFRESHED = "refreshed"
    REMOVED = "removed"
    INVALIDATED = "invalidated"
