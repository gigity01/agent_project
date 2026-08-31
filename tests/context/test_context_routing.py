"""Context Selection 路由决策、Turn Attribution 链归属与完成事务集成测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 路由阶段与只读事实：
   - 普通完整用户输入创建处于 `context_ready` 状态的 `ConversationTurn` 与 `ContextSelectionRecord`。
   - 路由阶段绝不预先创建正式 `ContextChainNode` 或修改资源历史事实；链节点仅在下游完成（complete_turn）时原子提交。
   - 路由锁保证同一 Conversation 的路由请求串行化。
2. 完成阶段与原子事务：
   - 完成 Turn 时提交 `TurnAttribution`（归属于已有链或新建链）及增量 `chain_updates`。
   - 数据库事务内原子完成：标记 Turn 为 completed、创建 Node、追加资源事实与事件、递增 resource_version 并更新 last_active_at。
   - 幂等性：重复提交同一完成请求保证幂等且不重复创建 Node。
3. 跨存储一致性与缓存隔离：
   - 数据库提交后刷新 Redis 热队列；Redis 故障不能回滚已提交的 MySQL 事实，降级为删除热队列 Key 触发后续预热。
"""

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
    from app.modules.context.application.context_service import ContextService
    from app.modules.context.application.dto import (
        ChainTurnUpdate,
        CompleteTurnCommand,
        ContextResourceInput,
        SendMessageCommand,
        TurnAttribution,
    )
    from app.modules.context.application.errors import (
        ContextConflictError,
        ContextValidationError,
    )
    from app.modules.context.application.resource_service import (
        ContextResourceService,
    )
    from app.modules.context.domain.enums import ContextTurnStatus
    from app.modules.context.domain.models import (
        ContextChain,
        ContextResourceQueue,
        ContextSelectionDecision,
    )
    from app.modules.context.domain.selection_policy import (
        derive_context_selection_mode,
        validate_context_selection,
    )
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
    from app.modules.context.infrastructure.persistence.models.context_selection_record import (
        ContextSelectionRecord,
    )
    from app.modules.context.infrastructure.persistence.models.conversation_turn import (
        ConversationTurn as ConversationTurnModel,
    )


class _AgentRouter:
    """测试用固定决策路由替身。"""
    def __init__(self, decision: ContextSelectionDecision) -> None:
        self.decision = decision
        self.inputs = []

    async def route(self, agent_input):
        self.inputs.append(agent_input)
        return self.decision


class _RouteLockManager:
    """测试用内存路由串行化锁管理器替身。"""
    def __init__(self) -> None:
        self.conversation_ids: list[str] = []

    @asynccontextmanager
    async def hold(self, conversation_id: str):
        self.conversation_ids.append(conversation_id)
        yield


class _EventLogger:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, **fields) -> bool:
        self.events.append({"event": event, **fields})
        return True


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
        queue = [
            item
            for item in self.queues.get(key, [])
            if item.resource_key not in set(removed_resource_keys)
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


def _domain_chain(
    chain_id: str,
    *,
    conversation_id: str = "conversation-1",
    archived: bool = False,
) -> ContextChain:
    return ContextChain(
        chain_id=chain_id,
        conversation_id=conversation_id,
        nodes=[],
        resource_queue=ContextResourceQueue(capacity=16),
        last_active_at=datetime.now(),
        archived=archived,
    )


class ContextSelectionValidationTest(unittest.TestCase):
    """验证 ContextSelectionDecision 的去重、模式推导与异常检测规则。"""

    def test_deduplicates_ids_and_derives_multi_context(self) -> None:
        """验证多链选择时自动去重并推导 selection_mode 为 multi_context。"""
        chains = [_domain_chain("chain-a"), _domain_chain("chain-b")]
        decision = validate_context_selection(
            ContextSelectionDecision(
                relevant_chain_ids=["chain-b", "chain-a", "chain-b"],
                reason_summary="Planner 需要两条历史链。",
            ),
            chains,
            conversation_id="conversation-1",
        )

        self.assertEqual(decision.relevant_chain_ids, ["chain-b", "chain-a"])
        self.assertEqual(
            derive_context_selection_mode(decision.relevant_chain_ids).value,
            "multi_context",
        )

    def test_unknown_chain_is_rejected(self) -> None:
        """验证选择不存在的 unknown chain_id 时抛出 ValueError。"""
        with self.assertRaisesRegex(ValueError, "selected unknown chain"):
            validate_context_selection(
                ContextSelectionDecision(
                    relevant_chain_ids=["chain-unknown"],
                    reason_summary="未知链。",
                ),
                [_domain_chain("chain-a")],
                conversation_id="conversation-1",
            )

    def test_archived_chain_is_rejected(self) -> None:
        """验证选择已归档的 chain 时抛出 ValueError。"""
        with self.assertRaisesRegex(ValueError, "selected archived chain"):
            validate_context_selection(
                ContextSelectionDecision(
                    relevant_chain_ids=["chain-a"],
                    reason_summary="归档链。",
                ),
                [_domain_chain("chain-a", archived=True)],
                conversation_id="conversation-1",
            )


class ContextServiceTest(unittest.IsolatedAsyncioTestCase):
    """验证 ContextService 消息发送路由、上下文选择持久化、Turn 完成及跨存储事务。"""

    def setUp(self) -> None:
        """初始化内存数据库、路由锁、资源服务、固定路由代理及事件收集器。"""
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.tables = [
            ConversationTurnModel.__table__,
            ContextChainModel.__table__,
            ContextChainNodeModel.__table__,
            ContextChainResource.__table__,
            ContextChainResourceEvent.__table__,
            ContextSelectionRecord.__table__,
        ]
        Base.metadata.create_all(self.engine, tables=self.tables)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.lock_manager = _RouteLockManager()
        self.queue_repository = _QueueRepository()
        self.record_factory = SQLAlchemyContextRecordFactory()
        self.resource_service = ContextResourceService(
            queue_repository=self.queue_repository,
            uow_factory=lambda: SQLAlchemyUnitOfWork(self.session_factory),
            record_factory=self.record_factory,
        )
        self.agent_router = _AgentRouter(
            ContextSelectionDecision(
                relevant_chain_ids=[],
                reason_summary="当前请求不需要历史上下文。",
            )
        )
        self.event_logger = _EventLogger()
        self.service = ContextService(
            agent_router=self.agent_router,
            route_lock_manager=self.lock_manager,
            resource_service=self.resource_service,
            uow_factory=lambda: SQLAlchemyUnitOfWork(self.session_factory),
            record_factory=self.record_factory,
            chain_mapper=build_context_chain,
            event_logger=self.event_logger,
        )

    def tearDown(self) -> None:
        Base.metadata.drop_all(
            self.engine,
            tables=list(reversed(self.tables)),
        )
        self.engine.dispose()

    def _insert_chain(
        self,
        chain_id: str,
        *,
        last_active_at: datetime | None = None,
        archived: bool = False,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                ContextChainModel(
                    chain_id=chain_id,
                    conversation_id="conversation-1",
                    resources={},
                    resource_version=0,
                    last_active_at=last_active_at or datetime.now(),
                    archived=archived,
                )
            )
            session.commit()

    def _insert_historical_chain(self, chain_id: str = "chain-history") -> None:
        with self.session_factory() as session:
            turn = ConversationTurnModel(
                turn_id="turn-history",
                conversation_id="conversation-1",
                user_input="历史问题",
                assistant_content="完整历史回答",
                assistant_compact="历史回答摘要",
                task_ids=["task-history"],
                task_result_summary="历史执行事实",
                status=ContextTurnStatus.COMPLETED.value,
                completed_at=datetime.now(),
            )
            chain = ContextChainModel(
                chain_id=chain_id,
                conversation_id="conversation-1",
                resources={},
                resource_version=0,
                last_active_at=datetime.now(),
                archived=False,
            )
            session.add_all([turn, chain])
            session.flush()
            session.add(
                ContextChainNodeModel(
                    node_id="node-history",
                    chain_id=chain_id,
                    turn_id=turn.turn_id,
                    sequence=0,
                    related_task_ids=["task-history"],
                    related_resource_refs=["document:7"],
                )
            )
            session.commit()

    async def _select(
        self,
        relevant_chain_ids: list[str],
        *,
        message: str = "当前问题",
    ):
        self.agent_router.decision = ContextSelectionDecision(
            relevant_chain_ids=relevant_chain_ids,
            reason_summary="测试选择。",
        )
        return await self.service.send_message(
            SendMessageCommand(
                conversation_id="conversation-1",
                message=message,
            )
        )

    async def test_selection_persists_read_set_without_chain_or_node(self) -> None:
        """验证路由选择阶段仅持久化 ContextSelectionRecord 并置 Turn 状态为 context_ready，绝不创建链或节点。"""
        package = await self._select([])

        with self.session_factory() as session:
            turn = session.query(ConversationTurnModel).one()
            selection = session.query(ContextSelectionRecord).one()
            chain_count = session.query(ContextChainModel).count()
            node_count = session.query(ContextChainNodeModel).count()

        self.assertEqual(package.context_chains, [])
        self.assertEqual(turn.status, ContextTurnStatus.CONTEXT_READY.value)
        self.assertEqual(selection.relevant_chain_ids, [])
        self.assertEqual(selection.selection_mode, "no_context")
        self.assertEqual(chain_count, 0)
        self.assertEqual(node_count, 0)
        event = self.event_logger.events[-1]
        self.assertEqual(event["event"], "context_selection_completed")
        self.assertEqual(event["context_selection_chain_count"], 0)
        self.assertEqual(event["context_selection_selected_count"], 0)
        self.assertEqual(event["context_selection_no_context_count"], 1)
        self.assertIn("context_selection_llm_duration", event)
        self.assertIn("context_selection_total_duration", event)

    async def test_observability_failure_does_not_change_selection(self) -> None:
        """验证可观测性记录异常不会改变路由选择结果或影响 Turn 状态推进。"""
        class _FailingEventLogger:
            def write(self, event: str, **fields) -> bool:
                raise OSError("metrics unavailable")

        self.service._event_logger = _FailingEventLogger()

        package = await self._select([])

        self.assertEqual(package.context_chain_ids, [])
        with self.session_factory() as session:
            turn = session.query(ConversationTurnModel).one()
        self.assertEqual(turn.status, ContextTurnStatus.CONTEXT_READY.value)

    async def test_current_turn_is_not_in_complete_historical_chain(self) -> None:
        """验证传递给 Agent 的历史链中不包含当前未完成的 Turn 节点（未决 Turn 不作为历史节点注入）。"""
        self._insert_historical_chain()
        package = await self._select(["chain-history"])

        agent_chain = self.agent_router.inputs[-1].chains[0]
        self.assertEqual(package.context_chain_ids, ["chain-history"])
        self.assertEqual([node.turn_id for node in agent_chain.nodes], ["turn-history"])
        self.assertNotIn(package.turn_id, [node.turn_id for node in agent_chain.nodes])
        projected = agent_chain.nodes[0].turn
        self.assertEqual(projected.assistant_content, "完整历史回答")
        self.assertEqual(projected.assistant_compact, "历史回答摘要")
        self.assertEqual(projected.task_result_summary, "历史执行事实")
        self.assertEqual(agent_chain.nodes[0].related_resource_refs, ["document:7"])
        with self.session_factory() as session:
            self.assertEqual(
                session.query(ContextChainNodeModel)
                .filter(ContextChainNodeModel.turn_id == package.turn_id)
                .count(),
                0,
            )

    async def test_no_context_does_not_force_latest_chain(self) -> None:
        """验证当路由决策为 no_context 时，即使存在活跃历史链也不会强制关联最新链。"""
        now = datetime.now()
        self._insert_chain("chain-old", last_active_at=now)
        self._insert_chain(
            "chain-new",
            last_active_at=now + timedelta(seconds=1),
        )

        package = await self._select([])

        self.assertEqual(package.decision.relevant_chain_ids, [])
        with self.session_factory() as session:
            self.assertEqual(session.query(ContextChainNodeModel).count(), 0)
            self.assertEqual(session.query(ContextChainModel).count(), 2)

    async def test_complete_multi_attribution_creates_two_nodes(self) -> None:
        """验证多链归属（multi_attribution）时在数据库中原子创建对应的两条链节点（同一 Turn 挂载多链）。"""
        self._insert_chain("chain-a")
        self._insert_chain("chain-b")
        package = await self._select(["chain-a", "chain-b"])

        response = await self.service.complete_turn(
            package.turn_id,
            CompleteTurnCommand(
                assistant_content="完成。",
                attribution=TurnAttribution(
                    existing_chain_ids=["chain-a", "chain-b"]
                ),
            ),
        )

        self.assertEqual(response.linked_chain_ids, ["chain-a", "chain-b"])
        with self.session_factory() as session:
            nodes = (
                session.query(ContextChainNodeModel)
                .filter(ContextChainNodeModel.turn_id == package.turn_id)
                .order_by(ContextChainNodeModel.chain_id)
                .all()
            )
        self.assertEqual([node.chain_id for node in nodes], ["chain-a", "chain-b"])

    async def test_attribution_can_differ_from_context_read_set(self) -> None:
        """验证下游完成时提交的归属链（Attribution）可以独立于路由阶段的只读候选集（Read Set）。"""
        self._insert_chain("chain-read")
        self._insert_chain("chain-write")
        package = await self._select(["chain-read"])

        response = await self.service.complete_turn(
            package.turn_id,
            CompleteTurnCommand(
                attribution=TurnAttribution(
                    existing_chain_ids=["chain-write"]
                )
            ),
        )

        self.assertEqual(response.linked_chain_ids, ["chain-write"])
        with self.session_factory() as session:
            node = session.query(ContextChainNodeModel).one()
        self.assertEqual(node.chain_id, "chain-write")

    async def test_complete_without_attribution_auto_creates_chain_and_node(self) -> None:
        """验证未显式指定归属时，Service 自动创建新链并建立关联节点。"""
        package = await self._select([])

        response = await self.service.complete_turn(
            package.turn_id,
            CompleteTurnCommand(assistant_content="需要一条新链。"),
        )

        self.assertEqual(len(response.linked_chain_ids), 1)
        with self.session_factory() as session:
            chain = session.query(ContextChainModel).one()
            node = session.query(ContextChainNodeModel).one()
            turn = session.query(ConversationTurnModel).one()
        self.assertEqual(chain.chain_id, response.linked_chain_ids[0])
        self.assertEqual(node.chain_id, chain.chain_id)
        self.assertEqual(node.turn_id, turn.turn_id)
        self.assertEqual(turn.status, ContextTurnStatus.COMPLETED.value)

    async def test_new_chain_node_and_resources_are_committed_together(self) -> None:
        """验证新建链、链节点、资源状态（ContextChainResource）与历史事件在单数据库事务内原子提交。"""
        package = await self._select([])
        new_chain_id = "chain-new"

        response = await self.service.complete_turn(
            package.turn_id,
            CompleteTurnCommand(
                assistant_content="已完成。",
                task_ids=["task-1"],
                task_result_summary="完成事实",
                attribution=TurnAttribution(
                    create_new_chain=True,
                    new_chain_id=new_chain_id,
                ),
                chain_updates=[
                    ChainTurnUpdate(
                        chain_id=new_chain_id,
                        related_task_ids=["task-1"],
                        related_resources=[
                            ContextResourceInput(
                                resource_type="result",
                                resource_id="result-1",
                            )
                        ],
                    )
                ],
            ),
        )

        self.assertEqual(response.linked_chain_ids, [new_chain_id])
        with self.session_factory() as session:
            node = session.query(ContextChainNodeModel).one()
            resource = session.query(ContextChainResource).one()
            event = session.query(ContextChainResourceEvent).one()
            chain = session.query(ContextChainModel).one()
        self.assertEqual(node.related_task_ids, ["task-1"])
        self.assertEqual(node.related_resource_refs, ["result:result-1"])
        self.assertEqual(resource.resource_key, "result:result-1")
        self.assertEqual(event.action, "seen")
        self.assertEqual(chain.resource_version, 1)
        self.assertEqual(
            self.queue_repository.versions[("conversation-1", new_chain_id)],
            1,
        )

    async def test_node_creation_failure_rolls_back_entire_completion(self) -> None:
        """验证多节点创建中途失败时，整个完成事务回滚，Turn 保持原状且不残留孤立节点。"""
        self._insert_chain("chain-a")
        self._insert_chain("chain-b")
        package = await self._select(["chain-a", "chain-b"])
        original = self.record_factory.context_chain_node
        call_count = 0

        def fail_second_node(**values):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("node persistence failed")
            return original(**values)

        with mock.patch.object(
            self.record_factory,
            "context_chain_node",
            side_effect=fail_second_node,
        ):
            with self.assertRaisesRegex(RuntimeError, "node persistence failed"):
                await self.service.complete_turn(
                    package.turn_id,
                    CompleteTurnCommand(
                        attribution=TurnAttribution(
                            existing_chain_ids=["chain-a", "chain-b"]
                        )
                    ),
                )

        with self.session_factory() as session:
            turn = session.get(ConversationTurnModel, package.turn_id)
            node_count = session.query(ContextChainNodeModel).count()
        self.assertEqual(turn.status, ContextTurnStatus.CONTEXT_READY.value)
        self.assertEqual(node_count, 0)

    async def test_repeated_complete_is_idempotent(self) -> None:
        """验证重复调用 complete_turn 具有幂等性，不重复插入节点与资源。"""
        package = await self._select([])
        command = CompleteTurnCommand(
            attribution=TurnAttribution(
                create_new_chain=True,
                new_chain_id="chain-idempotent",
            )
        )

        first = await self.service.complete_turn(package.turn_id, command)
        second = await self.service.complete_turn(package.turn_id, command)

        self.assertEqual(first.linked_chain_ids, ["chain-idempotent"])
        self.assertEqual(second.linked_chain_ids, ["chain-idempotent"])
        with self.session_factory() as session:
            self.assertEqual(session.query(ContextChainNodeModel).count(), 1)

    async def test_completed_turn_without_node_is_rejected_as_corrupt(self) -> None:
        """验证已完成但缺失链节点的异常状态轮次被拒绝并抛出 ContextConflictError。"""
        package = await self._select([])
        with self.session_factory() as session:
            turn = session.get(ConversationTurnModel, package.turn_id)
            turn.status = ContextTurnStatus.COMPLETED.value
            session.commit()

        with self.assertRaisesRegex(ContextConflictError, "缺少 Chain Attribution"):
            await self.service.complete_turn(
                package.turn_id,
                CompleteTurnCommand(),
            )

    async def test_selection_persistence_failure_marks_turn_failed(self) -> None:
        """验证路由选择记录持久化失败时将 Turn 推进到 failed 终态。"""
        with mock.patch.object(
            self.record_factory,
            "context_selection_record",
            side_effect=RuntimeError("selection persistence failed"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "selection persistence failed",
            ):
                await self._select([])

        with self.session_factory() as session:
            turn = session.query(ConversationTurnModel).one()
            self.assertEqual(turn.status, ContextTurnStatus.FAILED.value)
            self.assertEqual(session.query(ContextSelectionRecord).count(), 0)
            self.assertEqual(session.query(ContextChainNodeModel).count(), 0)

    async def test_chain_update_must_be_inside_attribution(self) -> None:
        """验证 chain_updates 中指定的 chain_id 必须包含在 Attribution 授权范围内，越界抛出 ContextValidationError。"""
        self._insert_chain("chain-a")
        self._insert_chain("chain-b")
        package = await self._select(["chain-a"])

        with self.assertRaisesRegex(
            ContextValidationError,
            "Attribution 范围",
        ):
            await self.service.complete_turn(
                package.turn_id,
                CompleteTurnCommand(
                    attribution=TurnAttribution(
                        existing_chain_ids=["chain-a"]
                    ),
                    chain_updates=[ChainTurnUpdate(chain_id="chain-b")],
                ),
            )

    async def test_redis_refresh_failure_keeps_committed_resource_facts(self) -> None:
        """验证 Redis 缓存刷新失败时保留已提交的 MySQL 数据库事实，并主动从缓存中失效该链。"""
        package = await self._select([])
        self.queue_repository.fail_refresh = True

        response = await self.service.complete_turn(
            package.turn_id,
            CompleteTurnCommand(
                attribution=TurnAttribution(
                    create_new_chain=True,
                    new_chain_id="chain-resource",
                ),
                chain_updates=[
                    ChainTurnUpdate(
                        chain_id="chain-resource",
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

        self.assertEqual(response.turn.status, ContextTurnStatus.COMPLETED.value)
        with self.session_factory() as session:
            self.assertEqual(
                session.query(ContextChainResource).one().resource_key,
                "document:13",
            )
            self.assertEqual(
                session.query(ContextChainResourceEvent).one().action,
                "seen",
            )
        self.assertEqual(
            self.queue_repository.invalidated,
            [("conversation-1", "chain-resource")],
        )

    async def test_resource_history_refresh_and_removal_are_preserved(self) -> None:
        """验证资源的多轮刷新（use_count 累加）与显式移除（active=False，action=removed）历史完整保留。"""
        first = await self._select([])
        await self.service.complete_turn(
            first.turn_id,
            CompleteTurnCommand(
                attribution=TurnAttribution(
                    create_new_chain=True,
                    new_chain_id="chain-resource-history",
                ),
                chain_updates=[
                    ChainTurnUpdate(
                        chain_id="chain-resource-history",
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
        second = await self._select(["chain-resource-history"])
        await self.service.complete_turn(
            second.turn_id,
            CompleteTurnCommand(
                attribution=TurnAttribution(
                    existing_chain_ids=["chain-resource-history"]
                ),
                chain_updates=[
                    ChainTurnUpdate(
                        chain_id="chain-resource-history",
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
            chain = session.get(ContextChainModel, "chain-resource-history")
        self.assertFalse(resources["document:A"].active)
        self.assertTrue(resources["document:B"].active)
        self.assertEqual(resources["document:B"].use_count, 2)
        self.assertEqual(chain.resource_version, 2)
        self.assertEqual(
            sorted(event.action for event in events),
            ["refreshed", "removed", "seen", "seen"],
        )


if __name__ == "__main__":
    unittest.main()
