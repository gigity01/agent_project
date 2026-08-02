"""Agent Tool 调用审计与统一执行边界。"""

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
    def write(self, event: dict[str, Any]) -> bool:
        ...


class AgentToolAuditLogger:
    """为每次 Tool 调用创建带关联上下文的非阻断审计记录。"""

    def __init__(self, writer: AgentToolAuditWriter | None = None) -> None:
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
        invocation = AgentToolInvocationAudit(
            writer=self._writer,
            context=context,
            tool_name=tool_name,
            resource_refs=resource_refs,
        )
        invocation.started()
        return invocation


class AgentToolInvocationAudit:
    """记录单次调用的开始和唯一终态。"""

    def __init__(
        self,
        *,
        writer: AgentToolAuditWriter,
        context: AgentToolContext,
        tool_name: str,
        resource_refs: list[str],
    ) -> None:
        self._writer = writer
        self._context = context
        self._tool_name = tool_name
        self._resource_refs = list(resource_refs)
        self._invocation_id = uuid4().hex
        self._started_at_ns = monotonic_ns()

    @property
    def duration_ms(self) -> int:
        return (monotonic_ns() - self._started_at_ns) // 1_000_000

    def _write(self, event: str, **fields: Any) -> None:
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
            logger.exception("Agent Tool 审计写入失败")

    def started(self) -> None:
        self._write("agent_tool_invocation_started")

    def succeeded(self, result_code: str) -> None:
        self._write(
            "agent_tool_invocation_succeeded",
            result_code=result_code,
            retryable=False,
        )

    def rejected(self, details: ToolErrorDetails) -> None:
        self._write(
            "agent_tool_invocation_rejected",
            result_code=details.result_code,
            retryable=details.retryable,
        )

    def failed(self, details: ToolErrorDetails) -> None:
        self._write(
            "agent_tool_invocation_failed",
            result_code=details.result_code,
            retryable=details.retryable,
        )


@dataclass(frozen=True)
class ToolCallExecution(Generic[T]):
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
    """执行权限检查、Use Case 调用和成对审计。"""
    invocation = context.audit_logger.start(
        context=context,
        tool_name=tool_name,
        resource_refs=resource_refs,
    )
    try:
        require_permissions(context.permissions, required_permissions)
        value = operation()
    except Exception as exc:
        details = classify_tool_error(exc, resource_refs=resource_refs)
        if details.outcome == "rejected":
            invocation.rejected(details)
        else:
            invocation.failed(details)
        return ToolCallExecution(error=details)

    invocation.succeeded(success_result_code)
    return ToolCallExecution(value=value)
