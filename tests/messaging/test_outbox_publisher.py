"""Outbox Publisher 的可靠发布状态测试。"""

from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.database.model_registry import load_all_models
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.modules.messaging.application.outbox import OutboxPublisher
from app.modules.messaging.infrastructure.persistence.models import OutboxEvent


class _Publisher:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, **event) -> None:
        self.events.append(event)


class OutboxPublisherTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        load_all_models()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        Base.metadata.create_all(self.engine, tables=[OutboxEvent.__table__])
        with self.session_factory() as session:
            session.add(
                OutboxEvent(
                    event_id="event-1",
                    event_type="runtime.plan_wakeup",
                    aggregate_type="plan",
                    aggregate_id="plan-1",
                    payload_json={"plan_id": "plan-1"},
                    status="pending",
                    attempts=0,
                    available_at=datetime.now(),
                )
            )
            session.commit()

    async def asyncTearDown(self) -> None:
        Base.metadata.drop_all(self.engine, tables=[OutboxEvent.__table__])
        self.engine.dispose()

    async def test_publishes_pending_event_once_and_marks_it_published(self) -> None:
        publisher = _Publisher()
        use_case = OutboxPublisher(
            uow_factory=lambda: SQLAlchemyUnitOfWork(self.session_factory),
            publisher=publisher,
        )
        self.assertEqual(await use_case.publish_batch(), 1)
        self.assertEqual(await use_case.publish_batch(), 0)
        self.assertEqual(publisher.events[0]["event_id"], "event-1")
        with self.session_factory() as session:
            event = session.get(OutboxEvent, "event-1")
            self.assertEqual(event.status, "published")
            self.assertIsNotNone(event.published_at)


if __name__ == "__main__":
    unittest.main()
