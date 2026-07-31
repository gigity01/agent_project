"""Context 路由、完成回写和确定性校验的离线测试。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import os
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main_config import environment


with (
    mock.patch.object(environment, "load_local_env_file", lambda _: None),
    mock.patch.dict(
        os.environ,
        {
            "SQLALCHEMY_DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "DASHSCOPE_API_KEY": "context-test-placeholder",
        },
    ),
):
    from app.constants.context_turn_status import ContextTurnStatus
    from app.db.session import Base
    from app.db.uow.sqlalchemy import SQLAlchemyUnitOfWork
    from app.modules.context.infrastructure.persistence.mapper import (
        SQLAlchemyContextRecordFactory,
        build_context_chain,
    )
    from app.models.context_chain import ContextChain as ContextChainModel
    from app.models.context_chain_node import (
        ContextChainNode as ContextChainNodeModel,
    )
    from app.models.context_chain_resource import ContextChainResource
    from app.models.context_chain_resource_event import (
        ContextChainResourceEvent,
    )
    from app.models.context_route_record import ContextRouteRecord
    from app.models.conversation_turn import (
        ConversationTurn as ConversationTurnModel,
    )
    from app.modules.context.domain.enums import ContextRouteMode
    from app.modules.context.domain.models import (
        ContextChain,
        ContextResourceQueue,
        ContextRouteDecision,
    )
    from app.modules.context.domain.route_policy import (
        validate_route_decision,
    )
    from app.schemas.context import (
        CompleteContextTurnRequest,
        ContextChainTurnUpdate,
        ContextResourceInput,
        ContextRouteRequest,
    )
    from app.modules.context.application.context_service import ContextService
    from app.modules.context.application.resource_service import (
        ContextResourceService,
    )


class _AgentRouter:
    def __init__(self, decision: ContextRouteDecision) -> None:
        self.decision = decision
        self.inputs = []

    async def route(self, agent_input):
        self.inputs.append(agent_input)
        return self.decision


class _RouteLockManager:
    def __init__(self) -> None:
        self.conversation_ids: list[str] = []

    @asynccontextmanager
    async def hold(self, conversation_id: str):
        self.conversation_ids.append(conversation_id)
        yield


class _QueueRepository:
    def __init__(self, *, capacity: int = 4) -> None:
        self.capacity = capacity
        self.queues = {}
        self.versions = {}
        self.invalidated = []
        self.fail_refresh = False

    async def get(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        expected_version: int,
    ):
        key = (conversation_id, chain_id)
        if self.versions.get(key) != expected_version:
            return None
        return ContextResourceQueue(
            capacity=self.capacity,
            items=list(self.queues.get(key, [])),
        )

    async def replace(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        resources,
        database_version: int,
    ) -> None:
        key = (conversation_id, chain_id)
        self.queues[key] = list(resources)
        self.versions[key] = database_version

    async def refresh(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        resources,
        removed_resource_keys,
        expected_previous_version: int,
        database_version: int,
    ) -> bool:
        if self.fail_refresh:
            raise RuntimeError("Redis unavailable")
        key = (conversation_id, chain_id)
        current_version = self.versions.get(key)
        if (
            current_version is not None
            and current_version != expected_previous_version
        ):
            return False
        if current_version is None and expected_previous_version != 0:
            return False
        queue = list(self.queues.get(key, []))
        removed_set = set(removed_resource_keys)
        queue = [
            item
            for item in queue
            if item.resource_key not in removed_set
        ]
        for resource in resources:
            queue = [
                item
                for item in queue
                if item.resource_key != resource.resource_key
            ]
            queue.append(resource)
        self.queues[key] = queue[-self.capacity :]
        self.versions[key] = database_version
        return True

    async def invalidate(
        self,
        *,
        conversation_id: str,
        chain_id: str,
    ) -> None:
        key = (conversation_id, chain_id)
        self.invalidated.append(key)
        self.queues.pop(key, None)
        self.versions.pop(key, None)


def _context_chain(
    chain_id: str,
    *,
    conversation_id: str = "conversation-1",
    last_active_at: datetime,
    archived: bool = False,
) -> ContextChain:
    return ContextChain(
        chain_id=chain_id,
        conversation_id=conversation_id,
        nodes=[],
        resource_queue=ContextResourceQueue(capacity=16),
        last_active_at=last_active_at,
        archived=archived,
    )


class ContextRouteValidationTest(unittest.TestCase):
    def test_fallback_latest_is_normalized_by_code(self) -> None:
        now = datetime.now()
        chains = [
            _context_chain("chain-old", last_active_at=now),
            _context_chain(
                "chain-new",
                last_active_at=now + timedelta(seconds=1),
            ),
        ]
        raw_decision = ContextRouteDecision(
            selected_chain_ids=["chain-old"],
            create_new_chain=True,
            route_mode=ContextRouteMode.FALLBACK_LATEST,
            reason_summary="指代存在关联但无法确定具体链。",
        )

        decision = validate_route_decision(
            raw_decision,
            chains,
            conversation_id="conversation-1",
        )

        self.assertEqual(decision.selected_chain_ids, ["chain-new"])
        self.assertFalse(decision.create_new_chain)

    def test_existing_and_new_requires_both_parts(self) -> None:
        chain = _context_chain(
            "chain-a",
            last_active_at=datetime.now(),
        )
        decision = ContextRouteDecision(
            selected_chain_ids=[],
            create_new_chain=True,
            route_mode=ContextRouteMode.EXISTING_AND_NEW,
            reason_summary="包含已有内容和新内容。",
        )

        with self.assertRaisesRegex(
            ValueError,
            "existing_and_new requires",
        ):
            validate_route_decision(
                decision,
                [chain],
                conversation_id="conversation-1",
            )


class ContextServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[
                ConversationTurnModel.__table__,
                ContextChainModel.__table__,
                ContextChainNodeModel.__table__,
                ContextChainResource.__table__,
                ContextChainResourceEvent.__table__,
                ContextRouteRecord.__table__,
            ],
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.lock_manager = _RouteLockManager()
        self.queue_repository = _QueueRepository()
        self.record_factory = SQLAlchemyContextRecordFactory()
        self.resource_service = ContextResourceService(
            queue_repository=self.queue_repository,
            uow_factory=lambda: SQLAlchemyUnitOfWork(
                self.session_factory
            ),
            record_factory=self.record_factory,
        )
        self.agent_router = _AgentRouter(
            ContextRouteDecision(
                selected_chain_ids=[],
                create_new_chain=True,
                route_mode=ContextRouteMode.NEW_CHAIN,
                reason_summary="当前没有相关已有链。",
            )
        )
        self.service = ContextService(
            agent_router=self.agent_router,
            route_lock_manager=self.lock_manager,
            resource_service=self.resource_service,
            uow_factory=lambda: SQLAlchemyUnitOfWork(
                self.session_factory
            ),
            record_factory=self.record_factory,
            chain_mapper=build_context_chain,
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    async def test_route_and_complete_create_one_turn_and_one_new_chain(
        self,
    ) -> None:
        package = await self.service.route_context(
            ContextRouteRequest(
                conversation_id="conversation-1",
                user_input="设计一个新的日志告警模块。",
            )
        )

        self.assertEqual(package.selected_chains, [])
        self.assertIsNotNone(package.new_chain_id)
        self.assertEqual(len(self.agent_router.inputs), 1)
        self.assertEqual(self.agent_router.inputs[0].chains, [])

        response = await self.service.complete_turn(
            package.current_turn_id,
            CompleteContextTurnRequest(
                assistant_content="已完成日志告警模块设计。",
                task_ids=["task-1"],
                task_result_summary="设计完成。",
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=package.new_chain_id,
                        related_task_ids=["task-1"],
                        related_resources=[
                            ContextResourceInput(
                                resource_type="result",
                                resource_id="result-1",
                                relation="generated_result",
                                summary="日志告警模块设计结果",
                            )
                        ],
                    )
                ],
            ),
        )

        self.assertEqual(
            response.linked_chain_ids,
            [package.new_chain_id],
        )
        self.assertEqual(
            response.turn.status,
            ContextTurnStatus.COMPLETED.value,
        )
        with self.session_factory() as session:
            turns = session.query(ConversationTurnModel).all()
            chains = session.query(ContextChainModel).all()
            nodes = session.query(ContextChainNodeModel).all()
            resources = session.query(ContextChainResource).all()
            events = session.query(ContextChainResourceEvent).all()

        self.assertEqual(len(turns), 1)
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(nodes[0].turn_id, turns[0].turn_id)
        self.assertEqual(nodes[0].chain_id, chains[0].chain_id)
        self.assertEqual(nodes[0].related_task_ids, ["task-1"])
        self.assertEqual(
            nodes[0].related_resource_refs,
            ["result:result-1"],
        )
        self.assertEqual(chains[0].resource_version, 1)
        self.assertEqual(chains[0].resources, {})
        self.assertEqual(resources[0].resource_key, "result:result-1")
        self.assertEqual(resources[0].use_count, 1)
        self.assertTrue(resources[0].active)
        self.assertEqual(events[0].action, "seen")
        queue_key = ("conversation-1", package.new_chain_id)
        self.assertEqual(
            [
                item.resource_key
                for item in self.queue_repository.queues[queue_key]
            ],
            ["result:result-1"],
        )
        self.assertEqual(self.queue_repository.versions[queue_key], 1)
        self.assertEqual(
            self.lock_manager.conversation_ids,
            ["conversation-1", "conversation-1"],
        )

    async def test_complete_rejects_chain_outside_saved_route(self) -> None:
        package = await self.service.route_context(
            ContextRouteRequest(
                conversation_id="conversation-1",
                user_input="创建新上下文。",
            )
        )

        with self.assertRaisesRegex(
            Exception,
            "Context Chain 不在已路由范围内",
        ):
            await self.service.complete_turn(
                package.current_turn_id,
                CompleteContextTurnRequest(
                    chain_updates=[
                        ContextChainTurnUpdate(chain_id="other-chain")
                    ]
                ),
            )

    async def test_redis_refresh_failure_keeps_committed_resource_facts(
        self,
    ) -> None:
        package = await self.service.route_context(
            ContextRouteRequest(
                conversation_id="conversation-1",
                user_input="创建资源事实。",
            )
        )
        self.queue_repository.fail_refresh = True

        response = await self.service.complete_turn(
            package.current_turn_id,
            CompleteContextTurnRequest(
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=package.new_chain_id,
                        related_resources=[
                            ContextResourceInput(
                                resource_type="document",
                                resource_id="13",
                            )
                        ],
                    )
                ],
            ),
        )

        self.assertEqual(
            response.turn.status,
            ContextTurnStatus.COMPLETED.value,
        )
        with self.session_factory() as session:
            resource = session.query(ContextChainResource).one()
            event = session.query(ContextChainResourceEvent).one()
            chain = session.query(ContextChainModel).one()

        self.assertEqual(resource.resource_key, "document:13")
        self.assertEqual(event.action, "seen")
        self.assertEqual(chain.resource_version, 1)
        self.assertEqual(
            self.queue_repository.invalidated,
            [("conversation-1", package.new_chain_id)],
        )

    async def test_refreshes_and_removes_resources_without_losing_history(
        self,
    ) -> None:
        first_package = await self.service.route_context(
            ContextRouteRequest(
                conversation_id="conversation-1",
                user_input="处理文档 A 和 B。",
            )
        )
        await self.service.complete_turn(
            first_package.current_turn_id,
            CompleteContextTurnRequest(
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=first_package.new_chain_id,
                        related_resources=[
                            ContextResourceInput(
                                resource_type="document",
                                resource_id="A",
                            ),
                            ContextResourceInput(
                                resource_type="document",
                                resource_id="B",
                            ),
                        ],
                    )
                ],
            ),
        )
        await self.queue_repository.invalidate(
            conversation_id="conversation-1",
            chain_id=first_package.new_chain_id,
        )

        self.agent_router.decision = ContextRouteDecision(
            selected_chain_ids=[first_package.new_chain_id],
            create_new_chain=False,
            route_mode=ContextRouteMode.SINGLE_MATCH,
            reason_summary="继续已有文档链。",
        )
        second_package = await self.service.route_context(
            ContextRouteRequest(
                conversation_id="conversation-1",
                user_input="继续使用 B，移除 A。",
            )
        )
        self.assertEqual(
            [
                item.resource_key
                for item in second_package.selected_chains[
                    0
                ].resource_queue.items
            ],
            ["document:A", "document:B"],
        )

        await self.service.complete_turn(
            second_package.current_turn_id,
            CompleteContextTurnRequest(
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=first_package.new_chain_id,
                        related_resources=[
                            ContextResourceInput(
                                resource_type="document",
                                resource_id="B",
                                summary="当前核心文档",
                            )
                        ],
                        removed_resource_keys=["document:A"],
                    )
                ],
            ),
        )

        with self.session_factory() as session:
            resources = {
                item.resource_key: item
                for item in session.query(ContextChainResource).all()
            }
            events = session.query(ContextChainResourceEvent).all()
            chain = session.query(ContextChainModel).one()

        self.assertFalse(resources["document:A"].active)
        self.assertIsNotNone(resources["document:A"].removed_at)
        self.assertTrue(resources["document:B"].active)
        self.assertEqual(resources["document:B"].use_count, 2)
        self.assertEqual(resources["document:B"].summary, "当前核心文档")
        self.assertEqual(chain.resource_version, 2)
        self.assertEqual(
            sorted(event.action for event in events),
            ["refreshed", "removed", "seen", "seen"],
        )
        queue_key = ("conversation-1", first_package.new_chain_id)
        self.assertEqual(
            [
                item.resource_key
                for item in self.queue_repository.queues[queue_key]
            ],
            ["document:B"],
        )


if __name__ == "__main__":
    unittest.main()
