"""Agent Tool 的安全错误分类。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal


ToolOutcome = Literal["rejected", "failed"]


class AgentToolPermissionError(PermissionError):
    """调用上下文缺少 Tool 所需权限。"""


class AgentToolScopeError(PermissionError):
    """Tool 请求超出当前 Agent Run 的授权资源范围。"""


class ToolNotAvailableError(LookupError):
    """指定角色的 Catalog 未注册目标 Tool。"""


@dataclass(frozen=True)
class ToolErrorDetails:
    """可以安全返回给模型的错误语义。"""

    outcome: ToolOutcome
    result_code: str
    message: str
    retryable: bool
    resource_refs: list[str]


def _is_retryable(error: Exception, status_code: int | None) -> bool:
    if status_code in {502, 503, 504}:
        return True

    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, (TimeoutError, ConnectionError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def classify_tool_error(
    error: Exception,
    *,
    resource_refs: list[str],
) -> ToolErrorDetails:
    """把应用拒绝和系统失败映射为稳定、安全的 Tool 结果。"""
    if isinstance(error, AgentToolPermissionError):
        return ToolErrorDetails(
            outcome="rejected",
            result_code="permission_denied",
            message="当前 Agent 没有调用该工具的权限",
            retryable=False,
            resource_refs=resource_refs,
        )

    if isinstance(error, AgentToolScopeError):
        return ToolErrorDetails(
            outcome="rejected",
            result_code="task_scope_violation",
            message="工具请求超出当前 Agent Run 的授权资源范围",
            retryable=False,
            resource_refs=resource_refs,
        )

    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int) and 400 <= status_code < 500:
        result_codes = {
            400: "invalid_request",
            401: "authentication_required",
            403: "permission_denied",
            404: "document_not_found",
            409: "document_state_conflict",
        }
        detail = getattr(error, "detail", None)
        message = detail if isinstance(detail, str) else "业务规则拒绝了该操作"
        explicit_result_code = getattr(error, "result_code", None)
        return ToolErrorDetails(
            outcome="rejected",
            result_code=(
                explicit_result_code
                if isinstance(explicit_result_code, str)
                else result_codes.get(status_code, "business_rejected")
            ),
            message=message,
            retryable=False,
            resource_refs=resource_refs,
        )

    return ToolErrorDetails(
        outcome="failed",
        result_code="tool_execution_failed",
        message="工具执行失败，请根据 retryable 决定是否重试",
        retryable=_is_retryable(error, status_code),
        resource_refs=resource_refs,
    )


def safe_tool_error_function(_context, _error: Exception) -> str:
    """处理 SDK 参数解析等外围异常时，不向模型暴露原始错误。"""
    return json.dumps(
        {
            "outcome": "rejected",
            "result_code": "invalid_tool_arguments",
            "message": "工具参数无效或无法解析",
            "retryable": False,
            "resource_refs": [],
        },
        ensure_ascii=False,
    )
