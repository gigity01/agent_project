"""Agent Tool 权限策略。"""

from collections.abc import Iterable

from app.agent_runtime.errors import AgentToolPermissionError


def require_permissions(
    granted_permissions: frozenset[str],
    required_permissions: Iterable[str],
) -> None:
    """要求调用上下文完整具备 Tool 声明的权限。"""
    missing = set(required_permissions) - granted_permissions
    if missing:
        raise AgentToolPermissionError("Agent Tool permission denied")
