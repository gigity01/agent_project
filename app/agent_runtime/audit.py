"""Agent Tool 调用审计与统一执行边界模块。

职责说明：
- 提供 Agent Tool 调用的生命周期审计追踪机制（开始、成功、拒绝、失败）。
- 统一封装工具执行入口 `execute_audited_tool_call`，集成本地权限检查、底层用例调用与错误分类。
- 将调用事件非阻塞地持久化至 JSONL 格式审计日志中，记录 trace_id、agent_run_id、operation_id、耗时与资源引用。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar
from uuid import uuid4

from app.agent_runtime.errors import ToolErrorDetails, classify_tool_error
from app.agent_runtime.policies import require_permissions
from app.config.settings import AGENT_TOOL_LOG_DIR
from app.shared.observability.jsonl_writer import JsonlEventWriter


if TYPE_CHECKING:
    from app.agent_runtime.context import AgentToolContext


logger = logging.getLogger(__name__)
T = TypeVar("T")


class AgentToolAuditWriter(Protocol):
    """Agent Tool 审计写入器协议接口。"""

    def write(self, event: dict[str, Any]) -> bool:
        """写入单条审计事件字典。

        参数:
            event: 包含调用上下文与执行结果的完整审计事件字典。

        返回:
            bool: 写入成功返回 True，失败或丢弃返回 False。
        """
        ...


class AgentToolAuditLogger:
    """Agent Tool 审计记录器。

    为每次 Tool 调用创建带有调用上下文（链路标识、执行者、资源引用等）的生命周期审计实例。
    """

    def __init__(self, writer: AgentToolAuditWriter | None = None) -> None:
        """初始化审计日志记录器。

        参数:
            writer: 审计事件写入器。未显式指定时，默认使用输出到 `AGENT_TOOL_LOG_DIR` 的 `JsonlEventWriter`。
        """
        self._writer = writer or JsonlEventWriter(
            log_dir=AGENT_TOOL_LOG_DIR,
            file_prefix="agent-tool",
        )

    def start(
        self,
        *,
        context: AgentToolContext,
        tool_name: str,
        resource_refs: list[str],
    ) -> AgentToolInvocationAudit:
        """开启一次 Tool 调用的生命周期审计并记录开始事件。

        参数:
            context: 当前 Agent Run 的工具调用上下文。
            tool_name: 被调用的工具唯一名称。
            resource_refs: 本次调用涉及的业务资源引用列表。

        返回:
            AgentToolInvocationAudit: 本次调用的生命周期审计追踪实例。
        """
        invocation = AgentToolInvocationAudit(
            writer=self._writer,
            context=context,
            tool_name=tool_name,
            resource_refs=resource_refs,
        )
        # 记录调用开始事件
        invocation.started()
        return invocation


class AgentToolInvocationAudit:
    """记录单次工具调用的生命周期事件与耗时统计。"""

    def __init__(
        self,
        *,
        writer: AgentToolAuditWriter,
        context: AgentToolContext,
        tool_name: str,
        resource_refs: list[str],
    ) -> None:
        """初始化单次调用审计追踪实例。

        参数:
            writer: 审计事件底层写入器。
            context: 当前调用上下文。
            tool_name: 工具名称。
            resource_refs: 关联的资源引用列表。
        """
        self._writer = writer
        self._context = context
        self._tool_name = tool_name
        self._resource_refs = list(resource_refs)
        self._invocation_id = uuid4().hex
        self._started_at_ns = monotonic_ns()

    @property
    def duration_ms(self) -> int:
        """获取自调用开始以来的累计耗时（毫秒）。"""
        return (monotonic_ns() - self._started_at_ns) // 1_000_000

    def _write(self, event: str, **fields: Any) -> None:
        """组装标准审计载荷并执行非阻塞安全写入。

        参数:
            event: 审计事件类型名称。
            **fields: 附加事件字段（如 result_code, retryable 等）。
        """
        payload = {
            "schema_version": 1,
            "event_id": uuid4().hex,
            "invocation_id": self._invocation_id,
            "event": event,
            "trace_id": self._context.trace_id,
            "agent_run_id": self._context.agent_run_id,
            "conversation_id": self._context.conversation_id,
            "turn_id": self._context.turn_id,
            "task_id": self._context.task_id,
            "workflow_id": self._context.workflow_id,
            "execution_id": self._context.execution_id,
            "operation_id": self._context.operation_id,
            "attempt": self._context.attempt,
            "agent_name": self._context.agent_name,
            "tool_name": self._tool_name,
            "actor_code": self._context.actor_code,
            "resource_refs": self._resource_refs,
            "duration_ms": self.duration_ms,
            **fields,
        }
        try:
            self._writer.write(payload)
        except Exception:
            # 审计写入失败不阻断核心业务流程，仅记录系统警告日志
            logger.exception("Agent Tool 审计写入失败")

    def started(self) -> None:
        """记录工具调用开始事件 (`agent_tool_invocation_started`)。"""
        self._write("agent_tool_invocation_started")

    def succeeded(self, result_code: str) -> None:
        """记录工具调用成功终态事件 (`agent_tool_invocation_succeeded`)。

        参数:
            result_code: 成功结果业务码。
        """
        self._write(
            "agent_tool_invocation_succeeded",
            result_code=result_code,
            retryable=False,
        )

    def rejected(self, details: ToolErrorDetails) -> None:
        """记录工具调用被业务规则或权限拒绝的终态事件 (`agent_tool_invocation_rejected`)。

        参数:
            details: 结构化错误详情对象。
        """
        self._write(
            "agent_tool_invocation_rejected",
            result_code=details.result_code,
            retryable=details.retryable,
        )

    def failed(self, details: ToolErrorDetails) -> None:
        """记录工具调用发生系统故障的终态事件 (`agent_tool_invocation_failed`)。

        参数:
            details: 结构化错误详情对象。
        """
        self._write(
            "agent_tool_invocation_failed",
            result_code=details.result_code,
            retryable=details.retryable,
        )


@dataclass(frozen=True)
class ToolCallExecution(Generic[T]):
    """封装工具调用执行结果与错误详情的数据容器。

    属性:
        value: 执行成功时返回的业务数据对象；失败或被拒绝时为 None。
        error: 执行被拒绝或失败时的结构化错误详情；成功时为 None。
    """

    value: T | None = None
    error: ToolErrorDetails | None = None


def execute_audited_tool_call(
    *,
    context: AgentToolContext,
    tool_name: str,
    required_permissions: tuple[str, ...],
    resource_refs: list[str],
    success_result_code: str,
    operation: Callable[[], T],
) -> ToolCallExecution[T]:
    """统一执行带权限检查、审计记录与错误分类的工具调用。

    执行流程：
    1. 启动生命周期审计并记录 started 事件。
    2. 校验上下文是否具备声明的 required_permissions 权限。
    3. 执行实际业务操作 `operation`。
    4. 若捕获异常，将其分类为 rejected（业务拒绝/权限拒绝）或 failed（系统故障），并记录对应终态审计。
    5. 若执行成功，记录 succeeded 终态审计并返回结果。

    参数:
        context: 当前工具调用上下文。
        tool_name: 工具名称。
        required_permissions: 该工具要求的权限列表。
        resource_refs: 关联的业务资源引用列表。
        success_result_code: 成功时记录的业务结果码。
        operation: 无参可调用对象，封装底层 Use Case 逻辑。

    返回:
        ToolCallExecution[T]: 包装业务返回值或分类后错误信息的执行结果对象。
    """
    invocation = context.audit_logger.start(
        context=context,
        tool_name=tool_name,
        resource_refs=resource_refs,
    )
    try:
        # 1. 严格检查调用权限
        require_permissions(context.permissions, required_permissions)
        # 2. 调用具体的业务用例
        value = operation()
    except Exception as exc:
        # 3. 捕获并分类错误，确定 outcome、result_code 与 retryable
        details = classify_tool_error(exc, resource_refs=resource_refs)
        if details.outcome == "rejected":
            invocation.rejected(details)
        else:
            invocation.failed(details)
        return ToolCallExecution(error=details)

    # 4. 成功终态审计
    invocation.succeeded(success_result_code)
    return ToolCallExecution(value=value)
