"""Agent Tool 权限策略与访问控制模块。

职责说明：
- 提供基于集合的最小权限检查函数 `require_permissions`。
- 确保当前 Agent Run 具备执行目标工具声明的全部权限，否则抛出 `AgentToolPermissionError` 阻止执行。
"""

from collections.abc import Iterable

from app.agent_runtime.errors import AgentToolPermissionError


def require_permissions(
    granted_permissions: frozenset[str],
    required_permissions: Iterable[str],
) -> None:
    """校验调用上下文是否完整具备目标工具声明的所有必要权限。

    检查逻辑：
    - 计算 `required_permissions - granted_permissions` 差集。
    - 若存在缺失权限，立即抛出 `AgentToolPermissionError` 拒绝调用。

    参数:
        granted_permissions: 当前调用上下文已授予的只读权限集合。
        required_permissions: 目标工具要求的一个或多个权限名称。

    异常:
        AgentToolPermissionError: 当已授予权限集合无法完全覆盖所需权限时抛出。
    """
    missing = set(required_permissions) - granted_permissions
    if missing:
        raise AgentToolPermissionError("Agent Tool permission denied")
