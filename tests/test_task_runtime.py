"""Task Runtime 同 Plan 串行与三段式状态流转测试。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.database.model_registry import load_all_models
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)
from app.modules.messaging.infrastructure.persistence.models import OutboxEvent
from app.modules.messaging.infrastructure.persistence.models import InboxEvent
from app.modules.planning.domain.enums import (
    PlanningCapabilityCode,
    PlanStatus,
    TaskStatus,
)
from app.modules.planning.infrastructure.persistence.models import (
    Plan,
    Task,
    TaskDependency,
)
from app.modules.task_runtime.application.dto import (
    ClaimNextTaskInput,
    TaskExecutorResult,
)
from app.modules.task_runtime.application.ports import (
    CompensatorRegistry,
    ExecutorRegistry,
    TaskRuntimePorts,
)
from app.modules.task_runtime.application.registry import (
    build_capability_registry,
)
from app.modules.task_runtime.application.runtime import TaskRuntimeService
from app.modules.task_runtime.infrastructure.persistence.models import (
    TaskExecution,
)


class _ProcessExecutor:
    async def execute(self, payload, context) -> TaskExecutorResult:
        return TaskExecutorResult(
            output_json={
                "document_id": payload.document_id,
                "status": "processed",
                "cleaned_uri": f"cleaned/{payload.document_id}.txt",
            },
            resource_refs=[f"document:{payload.document_id}"],
        )


class _NoopCompensator:
    def __init__(self) -> None:
        self.calls = []
        self.error: Exception | None = None

    async def compensate(self, *, operation_id, payload, context) -> None:
        self.calls.append((operation_id, payload.document_id, context))
        if self.error is not None:
            raise self.error


class TaskRuntimeTest(unittest.IsolatedAsyncioTestCase):
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
            TaskExecution.__table__,
            OutboxEvent.__table__,
            InboxEvent.__table__,
        ]
        Base.metadata.create_all(self.engine, tables=self.tables)
        with self.session_factory() as session:
            session.add(
                ConversationTurn(
                    turn_id="turn-runtime",
                    conversation_id="conversation-runtime",
                    user_input="依次处理两个文档",
                    task_ids=["task-1", "task-2"],
                    status="processing",
                )
            )
            session.add(
                Plan(
                    plan_id="plan-runtime",
                    workflow_id="workflow-runtime",
                    turn_id="turn-runtime",
                    parent_plan_id=None,
                    current_task_id=None,
                    status=PlanStatus.READY.value,
                    revision=1,
                    failure_code=None,
                    failure_reason=None,
                )
            )
            session.add_all(
                [
                    Task(
                        task_id="task-1",
                        plan_id="plan-runtime",
                        turn_id="turn-runtime",
                        task_ref="first",
                        capability_code=(
                            PlanningCapabilityCode.PROCESS_DOCUMENT.value
                        ),
                        input_json={"document_id": 1},
                        sequence=1,
                        status=TaskStatus.PENDING.value,
                        attempt_count=0,
                        max_attempts=3,
                    ),
                    Task(
                        task_id="task-2",
                        plan_id="plan-runtime",
                        turn_id="turn-runtime",
                        task_ref="second",
                        capability_code=(
                            PlanningCapabilityCode.PROCESS_DOCUMENT.value
                        ),
                        input_json={"document_id": 2},
                        sequence=2,
                        status=TaskStatus.PENDING.value,
                        attempt_count=0,
                        max_attempts=3,
                    ),
                ]
            )
            session.add(
                TaskDependency(
                    dependency_id="dependency-1",
                    plan_id="plan-runtime",
                    task_id="task-2",
                    depends_on_task_id="task-1",
                )
            )
            session.commit()

        self.compensator = _NoopCompensator()
        self.runtime = TaskRuntimeService(
            ports=TaskRuntimePorts(
                uow_factory=lambda: SQLAlchemyUnitOfWork(
                    self.session_factory
                ),
                task_execution_factory=TaskExecution,
                outbox_event_factory=OutboxEvent,
                inbox_event_factory=InboxEvent,
            ),
            capabilities=build_capability_registry(),
            executors=ExecutorRegistry(
                {"document.process": _ProcessExecutor()}
            ),
            compensators=CompensatorRegistry(
                {"document.process": self.compensator}
            ),
            retry_delay_seconds=0,
        )

    async def asyncTearDown(self) -> None:
        Base.metadata.drop_all(
            self.engine,
            tables=list(reversed(self.tables)),
        )
        self.engine.dispose()

    async def test_tasks_run_in_dependency_order_and_request_aggregation(self) -> None:
        first_claim = self.runtime.claim_next_task(
            ClaimNextTaskInput(plan_id="plan-runtime")
        )
        second_claim = self.runtime.claim_next_task(
            ClaimNextTaskInput(plan_id="plan-runtime")
        )
        self.assertEqual(first_claim.outcome, "claimed")
        self.assertEqual(second_claim.outcome, "already_running")
        self.assertTrue(first_claim.task.agent_run_id.startswith("agent_run_"))
        self.assertEqual(first_claim.task.turn_id, "turn-runtime")
        self.assertEqual(
            first_claim.task.conversation_id,
            "conversation-runtime",
        )
        self.runtime.complete_task(
            first_claim.task,
            {
                "document_id": 1,
                "status": "processed",
                "cleaned_uri": "cleaned/1.txt",
            },
            ["document:1"],
        )

        second = await self.runtime.execute_next("plan-runtime")
        self.assertEqual(second.outcome, "task_succeeded")
        self.assertEqual(second.task_id, "task-2")

        with self.session_factory() as session:
            plan = session.get(Plan, "plan-runtime")
            tasks = session.query(Task).order_by(Task.sequence).all()
            executions = (
                session.query(TaskExecution)
                .order_by(TaskExecution.started_at)
                .all()
            )
            outbox_types = [
                event.event_type
                for event in session.query(OutboxEvent)
                .order_by(OutboxEvent.created_at)
                .all()
            ]
            self.assertEqual(plan.status, "completed")
            self.assertIsNone(plan.current_task_id)
            self.assertEqual(
                [task.status for task in tasks],
                ["succeeded", "succeeded"],
            )
            self.assertEqual([item.attempt for item in executions], [1, 1])
            self.assertEqual(
                executions[0].agent_run_id,
                first_claim.task.agent_run_id,
            )
            self.assertEqual(
                executions[0].resource_refs_json,
                ["document:1"],
            )
            self.assertIn("runtime.plan_wakeup", outbox_types)
            self.assertEqual(outbox_types[-1], "aggregation.requested")

    async def test_stale_execution_is_compensated_before_retry(self) -> None:
        claimed = self.runtime.claim_next_task(
            ClaimNextTaskInput(plan_id="plan-runtime")
        )
        with self.session_factory() as session:
            task = session.get(Task, "task-1")
            task.started_at = datetime.now() - timedelta(seconds=301)
            session.commit()

        result = await self.runtime.execute_next("plan-runtime")

        self.assertEqual(result.outcome, "retry_scheduled")
        self.assertEqual(
            self.compensator.calls[0][0],
            claimed.task.operation_id,
        )
        with self.session_factory() as session:
            plan = session.get(Plan, "plan-runtime")
            task = session.get(Task, "task-1")
            execution = session.get(
                TaskExecution,
                claimed.task.execution_id,
            )
            self.assertIsNone(plan.current_task_id)
            self.assertEqual(task.status, "pending")
            self.assertEqual(execution.status, "compensated")
            self.assertEqual(
                execution.error_code,
                "execution_lease_expired",
            )

    async def test_compensation_failure_keeps_stale_task_owned(self) -> None:
        claimed = self.runtime.claim_next_task(
            ClaimNextTaskInput(plan_id="plan-runtime")
        )
        with self.session_factory() as session:
            task = session.get(Task, "task-1")
            task.started_at = datetime.now() - timedelta(seconds=301)
            session.commit()
        self.compensator.error = RuntimeError("compensation failed")

        with self.assertRaisesRegex(RuntimeError, "compensation failed"):
            await self.runtime.execute_next("plan-runtime")

        with self.session_factory() as session:
            plan = session.get(Plan, "plan-runtime")
            task = session.get(Task, "task-1")
            execution = session.get(
                TaskExecution,
                claimed.task.execution_id,
            )
            self.assertEqual(plan.current_task_id, task.task_id)
            self.assertEqual(task.status, "running")
            self.assertEqual(execution.status, "compensation_required")


if __name__ == "__main__":
    unittest.main()
