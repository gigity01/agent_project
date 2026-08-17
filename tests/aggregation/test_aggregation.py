"""Aggregation 从 TaskExecution 事实生成 Turn Completion 命令。"""

from __future__ import annotations

import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.database.model_registry import load_all_models
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.modules.aggregation.application.aggregate_plan import (
    AggregatePlanUseCase,
)
from app.modules.context.infrastructure.persistence.models.context_selection_record import (
    ContextSelectionRecord,
)
from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)
from app.modules.planning.infrastructure.persistence.models import Plan, Task
from app.modules.task_runtime.infrastructure.persistence.models import (
    TaskExecution,
)


class AggregationTest(unittest.IsolatedAsyncioTestCase):
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
            ContextSelectionRecord.__table__,
            Plan.__table__,
            Task.__table__,
            TaskExecution.__table__,
        ]
        Base.metadata.create_all(self.engine, tables=self.tables)
        with self.session_factory() as session:
            session.add(
                ConversationTurn(
                    turn_id="turn-aggregate",
                    conversation_id="conversation-1",
                    user_input="处理文档 7",
                    task_ids=["task-aggregate"],
                    status="processing",
                )
            )
            session.add(
                ContextSelectionRecord(
                    selection_id="selection-aggregate",
                    conversation_id="conversation-1",
                    current_turn_id="turn-aggregate",
                    relevant_chain_ids=["chain-1"],
                    selection_mode="single_context",
                    reason_summary="继续现有链",
                )
            )
            session.add(
                Plan(
                    plan_id="plan-aggregate",
                    workflow_id="workflow-aggregate",
                    turn_id="turn-aggregate",
                    parent_plan_id=None,
                    current_task_id=None,
                    status="completed",
                    revision=1,
                    failure_code=None,
                    failure_reason=None,
                )
            )
            session.add(
                Task(
                    task_id="task-aggregate",
                    plan_id="plan-aggregate",
                    turn_id="turn-aggregate",
                    task_ref="process",
                    capability_code="process_document",
                    input_json={"document_id": 7},
                    sequence=1,
                    status="succeeded",
                    attempt_count=1,
                    max_attempts=3,
                    output_json={"document_id": 7, "status": "processed"},
                )
            )
            session.add(
                TaskExecution(
                    execution_id="execution-aggregate",
                    task_id="task-aggregate",
                    plan_id="plan-aggregate",
                    workflow_id="workflow-aggregate",
                    attempt=1,
                    status="succeeded",
                    executor_code="document.process",
                    input_snapshot_json={"document_id": 7},
                    output_json={"document_id": 7, "status": "processed"},
                    resource_refs_json=["document:7"],
                    retryable=False,
                    operation_id="operation-aggregate",
                )
            )
            session.commit()

    async def asyncTearDown(self) -> None:
        Base.metadata.drop_all(
            self.engine,
            tables=list(reversed(self.tables)),
        )
        self.engine.dispose()

    async def test_aggregates_all_outputs_and_resource_refs(self) -> None:
        context_service = mock.Mock()
        context_service.complete_turn = mock.AsyncMock(return_value="completed")
        use_case = AggregatePlanUseCase(
            uow_factory=lambda: SQLAlchemyUnitOfWork(self.session_factory),
            context_service=context_service,
        )
        result = await use_case.execute("plan-aggregate")
        self.assertEqual(result, "completed")
        turn_id, command = context_service.complete_turn.await_args.args
        self.assertEqual(turn_id, "turn-aggregate")
        self.assertEqual(command.task_ids, ["task-aggregate"])
        self.assertEqual(
            command.attribution.existing_chain_ids,
            ["chain-1"],
        )
        self.assertFalse(command.attribution.create_new_chain)
        self.assertEqual(command.chain_updates[0].chain_id, "chain-1")
        self.assertEqual(
            command.chain_updates[0].related_resources[0].resource_key,
            "document:7",
        )


if __name__ == "__main__":
    unittest.main()
