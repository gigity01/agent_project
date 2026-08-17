"""Context Selection、完成回写和确定性校验的离线测试。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import os
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import environment


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
    from app.infrastructure.database.base import Base
    from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
    from app.modules.context.domain.enums import ContextTurnStatus
    from app.modules.context.infrastructure.persistence.mapper import (
        SQLAlchemyContextRecordFactory,
        build_context_chain,
    )
    from app.modules.context.infrastructure.persistence.models.context_chain import (
        ContextChain as ContextChainModel,
    )
    from app.modules.context.infrastructure.persistence.models.context_chain_node import (
        ContextChainNode as ContextChainNodeModel,
    )
    from app.modules.context.infrastructure.persistence.models.context_resource import (
        ContextChainResource,
    )
    from app.modules.context.infrastructure.persistence.models.context_resource_event import (
        ContextChainResourceEvent,
    )
    from app.modules.context.infrastructure.persistence.models.context_route_record import (
        ContextRouteRecord,
    )
    from app.modules.context.infrastructure.persistence.models.conversation_turn import (
        ConversationTurn as ConversationTurnModel,
    )
    from app.modules.context.domain.models import (
        ContextChain,
        ContextResourceQueue,
        ContextSelectionDecision,
    )
    from app.modules.context.domain.selection_policy import (
        derive_context_selection_mode,
        validate_context_selection,
    )
    from app.modules.context.presentation.schemas import (
        CompleteContextTurnRequest,
        ContextChainTurnUpdate,
        ContextResourceInput,
    )
    from app.modules.context.application.dto import SendMessageCommand
    from app.modules.context.application.errors import ContextConflictError
    from app.modules.context.application.context_service import ContextService
    from app.modules.context.application.resource_service import (
        ContextResourceService,
    )


class _AgentRouter:
    def __init__(self, decision: ContextSelectionDecision) -> None:
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


class ContextSelectionValidationTest(unittest.TestCase):
    def test_duplicate_ids_are_deduplicated_preserving_order(self) -> None:
        now = datetime.now()
        chains = [
            _context_chain("chain-old", last_active_at=now),
            _context_chain(
                "chain-new",
                last_active_at=now + timedelta(seconds=1),
            ),
        ]
        raw_decision = ContextSelectionDecision(
            relevant_chain_ids=["chain-new", "chain-old", "chain-new"],
            reason_summary="Planner 需要两条历史链。",
        )

        decision = validate_context_selection(
            raw_decision,
            chains,
            conversation_id="conversation-1",
        )

        self.assertEqual(
            decision.relevant_chain_ids,
            ["chain-new", "chain-old"],
        )
        self.assertEqual(
            derive_context_selection_mode(decision.relevant_chain_ids).value,
            "multi_context",
        )

    def test_unknown_chain_is_rejected(self) -> None:
        chain = _context_chain(
            "chain-a",
            last_active_at=datetime.now(),
        )
        decision = ContextSelectionDecision(
            relevant_chain_ids=["chain-unknown"],
            reason_summary="选择未知链。",
        )

        with self.assertRaisesRegex(
            ValueError,
            "selected unknown chain",
        ):
            validate_context_selection(
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
            ContextSelectionDecision(
                relevant_chain_ids=[],
                reason_summary="当前请求不需要历史上下文。",
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

    def _insert_chain(
        self,
        chain_id: str,
        *,
        last_active_at: datetime | None = None,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                ContextChainModel(
                    chain_id=chain_id,
                    conversation_id="conversation-1",
                    resources={},
                    resource_version=0,
                    last_active_at=last_active_at or datetime.now(),
                    archived=False,
                )
            )
            session.commit()

    async def _send(
        self,
        message: str,
        decision: ContextSelectionDecision,
    ):
        self.agent_router.decision = decision
        return await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message=message,
            )
        )

    def _legacy_new_chain_id(self, turn_id: str) -> str:
        """第一阶段 write-side 兼容层预建的 Chain ID。"""
        with self.session_factory() as session:
            record = (
                session.query(ContextRouteRecord)
                .filter(ContextRouteRecord.current_turn_id == turn_id)
                .one()
            )
            self.assertIsNotNone(record.new_chain_id)
            return record.new_chain_id

    async def test_route_and_complete_create_one_turn_and_one_new_chain(
        self,
    ) -> None:
        package = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="设计一个新的日志告警模块。",
            )
        )

        self.assertEqual(package.context_chains, [])
        new_chain_id = self._legacy_new_chain_id(package.turn_id)
        self.assertEqual(len(self.agent_router.inputs), 1)
        self.assertEqual(self.agent_router.inputs[0].chains, [])

        with self.session_factory() as session:
            routed_turn = session.query(ConversationTurnModel).one()
            routed_chain = session.query(ContextChainModel).one()
            placeholder = session.query(ContextChainNodeModel).one()
            route_record = session.query(ContextRouteRecord).one()

        self.assertEqual(
            routed_turn.status,
            ContextTurnStatus.CONTEXT_READY.value,
        )
        self.assertIsNone(routed_turn.assistant_content)
        self.assertIsNone(routed_turn.assistant_compact)
        self.assertEqual(routed_turn.task_ids, [])
        self.assertIsNone(routed_turn.task_result_summary)
        self.assertEqual(routed_chain.chain_id, new_chain_id)
        self.assertEqual(placeholder.chain_id, new_chain_id)
        self.assertEqual(placeholder.turn_id, package.turn_id)
        self.assertEqual(placeholder.sequence, 0)
        self.assertEqual(placeholder.related_task_ids, [])
        self.assertEqual(placeholder.related_resource_refs, [])
        self.assertEqual(route_record.new_chain_id, new_chain_id)

        response = await self.service.complete_turn(
            package.turn_id,
            CompleteContextTurnRequest(
                assistant_content="已完成日志告警模块设计。",
                task_ids=["task-1"],
                task_result_summary="设计完成。",
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=new_chain_id,
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
            [new_chain_id],
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
        queue_key = ("conversation-1", new_chain_id)
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

    async def test_second_message_loads_first_routed_chain(self) -> None:
        first = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="创建第一条上下文。",
            )
        )
        first_chain_id = self._legacy_new_chain_id(first.turn_id)
        second = await self._send(
            "继续第一条上下文。",
            ContextSelectionDecision(
                relevant_chain_ids=[first_chain_id],
                reason_summary="继续第一条上下文。",
            ),
        )

        self.assertEqual(len(self.agent_router.inputs), 2)
        second_input = self.agent_router.inputs[1]
        self.assertEqual(
            [chain.chain_id for chain in second_input.chains],
            [first_chain_id],
        )
        self.assertEqual(
            [node.turn_id for node in second_input.chains[0].nodes],
            [first.turn_id],
        )
        self.assertEqual(second.context_chain_ids, [first_chain_id])

        with self.session_factory() as session:
            nodes = (
                session.query(ContextChainNodeModel)
                .filter(
                    ContextChainNodeModel.chain_id == first_chain_id
                )
                .order_by(ContextChainNodeModel.sequence)
                .all()
            )

        self.assertEqual(
            [(node.turn_id, node.sequence) for node in nodes],
            [(first.turn_id, 0), (second.turn_id, 1)],
        )

    async def test_multi_match_creates_placeholder_for_every_chain(
        self,
    ) -> None:
        self._insert_chain("chain-a")
        self._insert_chain("chain-b")

        package = await self._send(
            "同时关联 A 和 B。",
            ContextSelectionDecision(
                relevant_chain_ids=["chain-a", "chain-b"],
                reason_summary="消息同时关联两条链。",
            ),
        )

        with self.session_factory() as session:
            nodes = (
                session.query(ContextChainNodeModel)
                .filter(ContextChainNodeModel.turn_id == package.turn_id)
                .order_by(ContextChainNodeModel.chain_id)
                .all()
            )

        self.assertEqual(
            [(node.chain_id, node.sequence) for node in nodes],
            [("chain-a", 0), ("chain-b", 0)],
        )

    async def test_single_context_does_not_create_an_extra_chain(self) -> None:
        self._insert_chain("chain-existing")

        package = await self._send(
            "继续已有内容并加入新主题。",
            ContextSelectionDecision(
                relevant_chain_ids=["chain-existing"],
                reason_summary="Planner 只需要已有上下文。",
            ),
        )

        with self.session_factory() as session:
            chains = session.query(ContextChainModel).all()
            nodes = (
                session.query(ContextChainNodeModel)
                .filter(ContextChainNodeModel.turn_id == package.turn_id)
                .order_by(ContextChainNodeModel.chain_id)
                .all()
            )

        self.assertEqual(len(chains), 1)
        self.assertEqual({node.chain_id for node in nodes}, {"chain-existing"})
        self.assertTrue(all(node.sequence == 0 for node in nodes))

    async def test_no_context_does_not_force_latest_chain(
        self,
    ) -> None:
        now = datetime.now()
        self._insert_chain("chain-old", last_active_at=now)
        self._insert_chain(
            "chain-new",
            last_active_at=now + timedelta(seconds=1),
        )

        package = await self._send(
            "继续刚才那个。",
            ContextSelectionDecision(
                relevant_chain_ids=[],
                reason_summary="Planner 不需要历史上下文。",
            ),
        )

        with self.session_factory() as session:
            nodes = (
                session.query(ContextChainNodeModel)
                .filter(ContextChainNodeModel.turn_id == package.turn_id)
                .all()
            )

        self.assertEqual(package.decision.relevant_chain_ids, [])
        self.assertNotIn(
            nodes[0].chain_id,
            {"chain-old", "chain-new"},
        )

    async def test_complete_turn_rejects_missing_placeholder(self) -> None:
        package = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="创建会被破坏的占位节点。",
            )
        )
        with self.session_factory() as session:
            node = session.query(ContextChainNodeModel).one()
            session.delete(node)
            session.commit()

        with self.assertRaisesRegex(
            ContextConflictError,
            "缺少路由阶段占位节点",
        ):
            await self.service.complete_turn(
                package.turn_id,
                CompleteContextTurnRequest(),
            )

        with self.session_factory() as session:
            turn = session.query(ConversationTurnModel).one()
            node_count = session.query(ContextChainNodeModel).count()

        self.assertEqual(turn.status, ContextTurnStatus.CONTEXT_READY.value)
        self.assertEqual(node_count, 0)

    async def test_repeated_complete_turn_is_idempotent(self) -> None:
        package = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="创建可幂等完成的上下文。",
            )
        )
        new_chain_id = self._legacy_new_chain_id(package.turn_id)
        command = CompleteContextTurnRequest(
            assistant_content="完成。",
            chain_updates=[
                ContextChainTurnUpdate(
                    chain_id=new_chain_id,
                    related_resources=[
                        ContextResourceInput(
                            resource_type="document",
                            resource_id="42",
                        )
                    ],
                )
            ],
        )

        first = await self.service.complete_turn(package.turn_id, command)
        second = await self.service.complete_turn(package.turn_id, command)

        with self.session_factory() as session:
            node_count = session.query(ContextChainNodeModel).count()
            resource = session.query(ContextChainResource).one()
            event_count = session.query(ContextChainResourceEvent).count()

        self.assertEqual(first.turn.status, ContextTurnStatus.COMPLETED.value)
        self.assertEqual(second.turn.status, ContextTurnStatus.COMPLETED.value)
        self.assertEqual(second.linked_chain_ids, [new_chain_id])
        self.assertEqual(node_count, 1)
        self.assertEqual(resource.use_count, 1)
        self.assertEqual(event_count, 1)

    async def test_sequence_follows_entry_order_not_completion_order(
        self,
    ) -> None:
        first = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="第一条消息。",
            )
        )
        first_chain_id = self._legacy_new_chain_id(first.turn_id)
        second = await self._send(
            "第二条消息。",
            ContextSelectionDecision(
                relevant_chain_ids=[first_chain_id],
                reason_summary="第二条消息继续第一条链。",
            ),
        )

        await self.service.complete_turn(
            second.turn_id,
            CompleteContextTurnRequest(),
        )
        await self.service.complete_turn(
            first.turn_id,
            CompleteContextTurnRequest(),
        )

        with self.session_factory() as session:
            nodes = (
                session.query(ContextChainNodeModel)
                .order_by(ContextChainNodeModel.sequence)
                .all()
            )

        self.assertEqual(
            [(node.turn_id, node.sequence) for node in nodes],
            [(first.turn_id, 0), (second.turn_id, 1)],
        )

    async def test_routing_persistence_failure_rolls_back_and_fails_turn(
        self,
    ) -> None:
        with mock.patch.object(
            self.record_factory,
            "context_chain_node",
            side_effect=RuntimeError("node persistence failed"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "node persistence failed",
            ):
                await self.service.send_message(
                    SendMessageCommand(
                        conversation_id="conversation-1",
                        message="触发路由事务回滚。",
                    )
                )

        with self.session_factory() as session:
            turn = session.query(ConversationTurnModel).one()
            route_count = session.query(ContextRouteRecord).count()
            chain_count = session.query(ContextChainModel).count()
            node_count = session.query(ContextChainNodeModel).count()

        self.assertEqual(turn.status, ContextTurnStatus.FAILED.value)
        self.assertEqual(route_count, 0)
        self.assertEqual(chain_count, 0)
        self.assertEqual(node_count, 0)

    async def test_complete_rejects_chain_outside_saved_route(self) -> None:
        package = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="创建新上下文。",
            )
        )

        with self.assertRaisesRegex(
            Exception,
            "Context Chain 不在已路由范围内",
        ):
            await self.service.complete_turn(
                package.turn_id,
                CompleteContextTurnRequest(
                    chain_updates=[
                        ContextChainTurnUpdate(chain_id="other-chain")
                    ]
                ),
            )

    async def test_redis_refresh_failure_keeps_committed_resource_facts(
        self,
    ) -> None:
        package = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="创建资源事实。",
            )
        )
        new_chain_id = self._legacy_new_chain_id(package.turn_id)
        self.queue_repository.fail_refresh = True

        response = await self.service.complete_turn(
            package.turn_id,
            CompleteContextTurnRequest(
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=new_chain_id,
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
            [("conversation-1", new_chain_id)],
        )

    async def test_refreshes_and_removes_resources_without_losing_history(
        self,
    ) -> None:
        first_package = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="处理文档 A 和 B。",
            )
        )
        first_chain_id = self._legacy_new_chain_id(first_package.turn_id)
        await self.service.complete_turn(
            first_package.turn_id,
            CompleteContextTurnRequest(
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=first_chain_id,
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
            chain_id=first_chain_id,
        )

        self.agent_router.decision = ContextSelectionDecision(
            relevant_chain_ids=[first_chain_id],
            reason_summary="继续已有文档链。",
        )
        second_package = await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message="继续使用 B，移除 A。",
            )
        )
        self.assertEqual(
            [
                item.resource_key
                for item in second_package.context_chains[
                    0
                ].resource_queue.items
            ],
            ["document:A", "document:B"],
        )

        await self.service.complete_turn(
            second_package.turn_id,
            CompleteContextTurnRequest(
                chain_updates=[
                    ContextChainTurnUpdate(
                        chain_id=first_chain_id,
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
        queue_key = ("conversation-1", first_chain_id)
        self.assertEqual(
            [
                item.resource_key
                for item in self.queue_repository.queues[queue_key]
            ],
            ["document:B"],
        )


if __name__ == "__main__":
    unittest.main()
