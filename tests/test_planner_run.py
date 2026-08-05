"""Planner 从 routed Turn 到 ready Plan 的单条闭环测试。"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agents import ModelSettings, RunContextWrapper
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent_runtime.audit import AgentToolAuditLogger
from app.agent_runtime.context import (
    ContextToolServices,
    DocumentToolServices,
    OperationsToolServices,
)
from app.agents.collectors import build_collector_agents
from app.agents.planner import build_planner_agent
from app.infrastructure.database.base import Base
from app.infrastructure.database.model_registry import load_all_models
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)
from app.modules.planning.agent_tools.planning_tools import (
    create_build_chunks_task_handler,
    create_index_vectors_task_handler,
    create_process_document_task_handler,
    finalize_plan_handler,
)
from app.modules.planning.agent_tools.schemas import (
    CreateBuildChunksTaskToolInput,
    CreateIndexVectorsTaskToolInput,
    CreateProcessDocumentTaskToolInput,
    FinalizePlanToolInput,
)
from app.modules.planning.application.dto import RunPlanningInput
from app.modules.planning.application.ports import PlanningApplicationPorts
from app.modules.planning.application.run_planning import RunPlanningUseCase
from app.modules.planning.application.use_cases import (
    build_planning_use_cases,
)
from app.modules.planning.infrastructure.persistence.models import Plan, Task
from app.modules.planning.infrastructure.persistence.models import TaskDependency
from app.modules.messaging.infrastructure.persistence.models import InboxEvent, OutboxEvent
from app.modules.clarification.infrastructure.persistence.models import ClarificationRequest


class _AuditWriter:
    def write(self, _event: dict) -> bool:
        return True


def _mock_document_services() -> DocumentToolServices:
    return DocumentToolServices(
        get_document=mock.Mock(),
        list_documents=mock.Mock(),
        search_documents=mock.Mock(),
        get_document_pipeline_state=mock.Mock(),
        list_document_artifacts=mock.Mock(),
        search_document_artifacts=mock.Mock(),
        list_parent_blocks=mock.Mock(),
        list_child_chunks=mock.Mock(),
        get_document_chunk_statistics=mock.Mock(),
        get_knowledge_base_statistics=mock.Mock(),
        process_document=mock.Mock(),
        build_chunks=mock.Mock(),
        index_vectors=mock.Mock(),
    )


class _ClosedLoopPlannerRunner:
    def __init__(self) -> None:
        self.active_collectors = 0
        self.max_active_collectors = 0
        self.user_input: str | None = None

    async def run(self, *, user_input: str, context) -> str:
        self.user_input = user_input

        async def collect() -> None:
            self.active_collectors += 1
            self.max_active_collectors = max(
                self.max_active_collectors,
                self.active_collectors,
            )
            await asyncio.sleep(0)
            self.active_collectors -= 1

        await asyncio.gather(collect(), collect(), collect())
        wrapper = RunContextWrapper(context)
        task_outputs = (
            create_process_document_task_handler(
                wrapper,
                CreateProcessDocumentTaskToolInput(
                    task_ref="process",
                    document_id=7,
                    sequence=1,
                ),
            ),
            create_build_chunks_task_handler(
                wrapper,
                CreateBuildChunksTaskToolInput(
                    task_ref="chunks",
                    document_id=7,
                    sequence=2,
                    depends_on_task_refs=["process"],
                ),
            ),
            create_index_vectors_task_handler(
                wrapper,
                CreateIndexVectorsTaskToolInput(
                    task_ref="vectors",
                    document_id=7,
                    sequence=3,
                    depends_on_task_refs=["chunks"],
                ),
            ),
        )
        if any(output.outcome != "succeeded" for output in task_outputs):
            raise AssertionError("Planning Task Tool 未成功")
        finalized = finalize_plan_handler(wrapper, FinalizePlanToolInput())
        if finalized.outcome != "succeeded":
            raise AssertionError("finalize_plan 未成功")
        return "该文本不是业务事实"


class PlannerRunTest(unittest.IsolatedAsyncioTestCase):
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
            ClarificationRequest.__table__,
        ]
        Base.metadata.create_all(self.engine, tables=self.tables)
        with self.session_factory() as session:
            session.add(
                ConversationTurn(
                    turn_id="turn-planner-1",
                    conversation_id="conversation-1",
                    user_input="处理、切块并索引文档 7",
                    task_ids=[],
                    status="routed",
                )
            )
            session.commit()

    async def asyncTearDown(self) -> None:
        Base.metadata.drop_all(
            self.engine,
            tables=list(reversed(self.tables)),
        )
        self.engine.dispose()

    async def test_routed_turn_runs_planner_and_publishes_database_plan(self) -> None:
        collectors = build_collector_agents(
            model="test-model",
            model_settings=ModelSettings(parallel_tool_calls=False),
        )
        configured_runner = build_planner_agent(
            model="test-model",
            model_settings=ModelSettings(parallel_tool_calls=False),
            collectors=collectors,
        )
        self.assertEqual(
            {tool.name for tool in configured_runner.agent.tools},
            {
                "collect_planning_evidence",
                "create_process_document_task",
                "create_build_chunks_task",
                "create_index_vectors_task",
                "finalize_plan",
                "mark_plan_unsupported",
            },
        )
        self.assertFalse(
            configured_runner.agent.model_settings.parallel_tool_calls
        )
        self.assertEqual(
            configured_runner.run_config.tool_execution.max_function_tool_concurrency,
            1,
        )
        self.assertIsNone(configured_runner.agent.output_type)
        self.assertEqual(
            [handoff.tool_name for handoff in configured_runner.agent.handoffs],
            ["clarification_handoff"],
        )
        self.assertEqual(
            configured_runner.agent.tool_use_behavior,
            {
                "stop_at_tool_names": [
                    "finalize_plan",
                    "mark_plan_unsupported",
                ]
            },
        )

        ports = PlanningApplicationPorts(
            uow_factory=lambda: SQLAlchemyUnitOfWork(self.session_factory),
            plan_factory=Plan,
            task_factory=Task,
            task_dependency_factory=TaskDependency,
            outbox_event_factory=OutboxEvent,
            inbox_event_factory=InboxEvent,
            clarification_request_factory=ClarificationRequest,
            integrity_error_type=IntegrityError,
        )
        planning_use_cases = build_planning_use_cases(ports)
        closed_loop_runner = _ClosedLoopPlannerRunner()
        run_planning = RunPlanningUseCase(
            ports=ports,
            planning_use_cases=planning_use_cases,
            planner_runner=closed_loop_runner,
            document_services=_mock_document_services(),
            context_services=ContextToolServices(),
            operations_services=OperationsToolServices(),
            audit_logger_factory=lambda: AgentToolAuditLogger(_AuditWriter()),
        )

        result = await run_planning.execute(
            RunPlanningInput(
                conversation_id="conversation-1",
                turn_id="turn-planner-1",
            )
        )

        self.assertEqual(closed_loop_runner.max_active_collectors, 3)
        self.assertEqual(
            closed_loop_runner.user_input,
            "处理、切块并索引文档 7",
        )
        self.assertEqual(result.status.value, "ready")
        self.assertEqual(len(result.task_ids), 3)
        self.assertIsNone(result.failure_reason)
        with self.session_factory() as session:
            plan = session.get(Plan, result.plan_id)
            tasks = (
                session.query(Task)
                .filter(Task.plan_id == result.plan_id)
                .order_by(Task.sequence.asc())
                .all()
            )
            turn = session.get(ConversationTurn, "turn-planner-1")
            self.assertEqual(plan.status, "ready")
            self.assertEqual(
                [task.status for task in tasks],
                ["pending", "pending", "pending"],
            )
            self.assertEqual(turn.task_ids, result.task_ids)


if __name__ == "__main__":
    unittest.main()
