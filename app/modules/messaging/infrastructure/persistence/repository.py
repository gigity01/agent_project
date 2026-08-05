"""Outbox/Inbox 仓储。"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.messaging.infrastructure.persistence.models import (
    InboxEvent,
    OutboxEvent,
)


class OutboxRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, event: OutboxEvent) -> OutboxEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def list_available_for_update(
        self,
        *,
        status: str,
        now: datetime,
        limit: int,
    ) -> list[OutboxEvent]:
        return (
            self.db.query(OutboxEvent)
            .filter(
                OutboxEvent.status == status,
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.created_at.asc(), OutboxEvent.event_id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
            .all()
        )

    def get_by_id_for_update(self, event_id: str) -> OutboxEvent | None:
        return (
            self.db.query(OutboxEvent)
            .filter(OutboxEvent.event_id == event_id)
            .with_for_update()
            .first()
        )


class InboxRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def exists(self, consumer_name: str, event_id: str) -> bool:
        return (
            self.db.query(InboxEvent)
            .filter(
                InboxEvent.consumer_name == consumer_name,
                InboxEvent.event_id == event_id,
            )
            .first()
            is not None
        )

    def add(self, event: InboxEvent) -> InboxEvent:
        self.db.add(event)
        self.db.flush()
        return event
