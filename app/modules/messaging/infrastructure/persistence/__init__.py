"""Messaging ORM 模型。"""

from app.modules.messaging.infrastructure.persistence.models import (
    InboxEvent,
    OutboxEvent,
)

__all__ = ["InboxEvent", "OutboxEvent"]
