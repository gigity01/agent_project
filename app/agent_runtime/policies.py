"""Agent Tool 权限策略与访问控制模块。"""

from collections.abc import Iterable

from app.agent_runtime.errors import AgentToolPermissionError


def require_permissions(
    granted_permissions: frozenset[str],
    required_permissions: Iterable[str],
) -> None:
    """校验调用上下文是否完整具备目标工具声明的所有必要权限。"""
    missing = set(required_permissions) - granted_permissions
    if missing:
        raise AgentToolPermissionError("Agent Tool permission denied")
