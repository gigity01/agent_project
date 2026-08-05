"""Clarification 跨 Turn 回答与 Replan 新 revision 测试。"""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.database.model_registry import load_all_models
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.modules.clarification.application.answer import (
    AnswerClarificationUseCase,
)
from app.modules.clarification.infrastructure.persistence.models import (
    ClarificationRequest,
)
from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)
from app.modules.messaging.infrastructure.persistence.models import (
    InboxEvent,
    OutboxEvent,
)
from app.modules.planning.application.dto import RunPlanningResult
from app.modules.planning.application.ports import PlanningApplicationPorts
from app.modules.planning.application.replan import (
    ReplanRequested,
    ReplanUseCase,
)
from app.modules.planning.domain.enums import PlanStatus
from app.modules.planning.infrastructure.persistence.models import (
    Plan,
    Task,
    TaskDependency,
)


class _RunPlanning:
    def __init__(self) -> None:
        self.calls = []

    async def execute_existing(self, command, plan_id):
        self.calls.append((command, plan_id))
        return RunPlanningResult(
            plan_id=plan_id,
            turn_id=command.turn_id,
            status=PlanStatus.RETRY_PENDING,
            task_ids=[],
            failure_reason="offline test",
        )


class ReplanClarificationTest(unittest.IsolatedAsyncioTestCase):
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
        self.tables = [
            ConversationTurn.__table__,
            Plan.__table__,
            Task.__table__,
            TaskDependency.__table__,
            OutboxEvent.__table__,
            InboxEvent.__table__,
            ClarificationRequest.__table__,
        ]
        Base.metadata.create_all(self.engine, tables=self.tables)
        with self.session_factory() as session:
            session.add_all(
                [
                    ConversationTurn(
                        turn_id="turn-question",
                        conversation_id="conversation-1",
                        user_input="处理那个文档",
                        assistant_content="请确认文档。",
                        task_ids=[],
                        status="completed",
                    ),
                    ConversationTurn(
                        turn_id="turn-answer",
                        conversation_id="conversation-1",
                        user_input="文档 7",
                        task_ids=[],
                        status="routed",
                    ),
                ]
            )
            session.add(
                Plan(
                    plan_id="plan-question",
                    workflow_id="workflow-1",
                    turn_id="turn-question",
                    parent_plan_id=None,
                    current_task_id=None,
                    status="needs_clarification",
                    revision=1,
                    failure_code="clarification_required",
                    failure_reason="文档不唯一",
                )
            )
            session.add(
                ClarificationRequest(
                    clarification_id="clarification-1",
                    conversation_id="conversation-1",
                    source_turn_id="turn-question",
                    source_plan_id="plan-question",
                    kind="resource",
                    reason="文档不唯一",
                    question="请确认文档。",
                    required_information_json=["document_id"],
                    known_resource_refs_json=[],
                    status="open",
                    answer_turn_id=None,
                )
            )
            session.commit()

    async def asyncTearDown(self) -> None:
        Base.metadata.drop_all(
            self.engine,
            tables=list(reversed(self.tables)),
        )
        self.engine.dispose()

    async def test_answer_creates_replan_event_and_new_revision(self) -> None:
        uow_factory = lambda: SQLAlchemyUnitOfWork(self.session_factory)
        answer = AnswerClarificationUseCase(
            uow_factory=uow_factory,
            outbox_event_factory=OutboxEvent,
        )
        source_plan_id = answer.execute(
            conversation_id="conversation-1",
            answer_turn_id="turn-answer",
        )
        self.assertEqual(source_plan_id, "plan-question")
        with self.session_factory() as session:
            event = session.query(OutboxEvent).one()
            request = session.get(ClarificationRequest, "clarification-1")
            answer_turn = session.get(ConversationTurn, "turn-answer")
            self.assertEqual(request.status, "answered")
            self.assertEqual(request.answer_turn_id, "turn-answer")
            self.assertEqual(answer_turn.status, "processing")

        runner = _RunPlanning()
        ports = PlanningApplicationPorts(
            uow_factory=uow_factory,
            plan_factory=Plan,
            task_factory=Task,
            task_dependency_factory=TaskDependency,
            outbox_event_factory=OutboxEvent,
            inbox_event_factory=InboxEvent,
            clarification_request_factory=ClarificationRequest,
            integrity_error_type=IntegrityError,
        )
        replan = ReplanUseCase(ports=ports, run_planning=runner)
        result = await replan.execute(
            ReplanRequested(event_id=event.event_id, **event.payload_json)
        )
        self.assertEqual(result.status, PlanStatus.RETRY_PENDING)
        with self.session_factory() as session:
            old_plan = session.get(Plan, "plan-question")
            new_plan = (
                session.query(Plan).filter(Plan.revision == 2).one()
            )
            self.assertEqual(old_plan.status, "superseded")
            self.assertEqual(new_plan.turn_id, "turn-answer")
            self.assertEqual(new_plan.workflow_id, "workflow-1")
            self.assertEqual(new_plan.parent_plan_id, "plan-question")
            self.assertEqual(session.query(InboxEvent).count(), 1)


if __name__ == "__main__":
    unittest.main()
