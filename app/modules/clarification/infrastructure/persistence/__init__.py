"""Clarification 持久化模块。

导出 ClarificationRequest ORM 实体模型。
"""

from app.modules.clarification.infrastructure.persistence.models import (
    ClarificationRequest,
)

__all__ = ["ClarificationRequest"]
