"""Clarification 领域枚举定义。"""

from __future__ import annotations

from enum import Enum


class ClarificationStatus(str, Enum):
    """澄清请求生命周期状态枚举。

    状态流转说明：
    - OPEN: 澄清请求已创建，正在等待用户提供补充输入。
    - ANSWERED: 用户已提交回答，正在触发并等待基于澄清的 Plan 重规划及 Task 执行。
    - RESOLVED: 新 Plan 下所有 Task 已成功执行并完成结果聚合，澄清流程正式完结。
    - EXPIRED: 澄清请求超时未回答，已失效（预留）。
    """

    OPEN = "open"
    ANSWERED = "answered"
    RESOLVED = "resolved"
    EXPIRED = "expired"
