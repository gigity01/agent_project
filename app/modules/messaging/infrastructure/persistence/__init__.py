"""Messaging 持久化模块。

导出 OutboxEvent 与 InboxEvent SQLAlchemy ORM 持久化模型。
"""

from app.modules.messaging.infrastructure.persistence.models import (
    InboxEvent,
    OutboxEvent,
)

__all__ = ["InboxEvent", "OutboxEvent"]
