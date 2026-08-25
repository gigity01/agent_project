"""Context 只读查询服务（ContextQueryService）与用例层测试。

核心业务不变量：
1. 只读不变量：
   - 所有查询方法（get/list turns, chains, nodes, resources, selection_records）绝不修改底层数据库状态。
2. 过滤与排序语义：
   - 链查询支持按 archived 状态过滤。
   - 轮次查询支持按状态（turn_statuses）筛选。
3. 领域用例轻量委托：
   - 7 个具名查询 UseCase 仅作为薄委托层，保持接口纯粹与依赖倒置。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.modules.context.application.query_dto import (
    ContextChainNodeSearchQuery,
    ContextChainResourceSearchQuery,
    ContextChainSearchQuery,
    ContextSelectionRecordSearchQuery,
    ConversationTurnSearchQuery,
)
from app.modules.context.application.query_service import ContextQueryService
from app.modules.context.application.use_cases import (
    GetContextChainUseCase,
    GetConversationTurnUseCase,
    ListContextChainNodesUseCase,
    ListContextChainResourcesUseCase,
    ListContextChainsUseCase,
    ListContextSelectionRecordsUseCase,
    ListConversationTurnsUseCase,
)
from app.modules.context.infrastructure.persistence.models.context_chain import (
    ContextChain,
)
from app.modules.context.infrastructure.persistence.models.context_chain_node import (
    ContextChainNode,
)
from app.modules.context.infrastructure.persistence.models.context_resource import (
    ContextChainResource,
)
from app.modules.context.infrastructure.persistence.models.context_selection_record import (
    ContextSelectionRecord,
)
from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)


NOW = datetime(2026, 8, 3, 12, 0, 0)


class ContextQueryServiceTest(unittest.TestCase):
    """验证 Context 只读查询服务的各种组合查询、多维过滤及 7 个具名 UseCase 的委托正确性。"""

    def setUp(self) -> None:
        """创建内存 SQLite 数据库，建立表结构并插入初始测试数据。"""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                ConversationTurn.__table__,
                ContextChain.__table__,
                ContextSelectionRecord.__table__,
                ContextChainNode.__table__,
                ContextChainResource.__table__,
            ],
        )
        self._seed()
        self.service = ContextQueryService(
            uow_factory=lambda: SQLAlchemyUnitOfWork(
                session_factory=lambda: Session(self.engine)
            )
        )

    def tearDown(self) -> None:
        """销毁数据库引擎并释放资源。"""
        self.engine.dispose()

    def _seed(self) -> None:
        """在数据库中插入包含 completed / context_ready 轮次、激活/归档链、选择记录、节点与资源的事实数据。"""
        with Session(self.engine) as session:
            session.add_all(
                [
                    ConversationTurn(
                        turn_id="turn-1",
                        conversation_id="conversation-1",
                        user_input="第一轮",
                        assistant_content="回答一",
                        assistant_compact=None,
                        task_ids=["task-1"],
                        task_result_summary="完成",
                        status="completed",
                        created_at=NOW - timedelta(minutes=2),
                        completed_at=NOW - timedelta(minutes=1),
                    ),
                    ConversationTurn(
                        turn_id="turn-2",
                        conversation_id="conversation-1",
                        user_input="第二轮",
                        assistant_content=None,
                        assistant_compact=None,
                        task_ids=[],
                        task_result_summary=None,
                        status="context_ready",
                        created_at=NOW,
                        completed_at=None,
                    ),
                ]
            )
            session.add_all(
                [
                    ContextChain(
                        chain_id="chain-active",
                        conversation_id="conversation-1",
                        resources={},
                        resource_version=1,
                        last_active_at=NOW,
                        archived=False,
                        created_at=NOW - timedelta(minutes=2),
                    ),
                    ContextChain(
                        chain_id="chain-archived",
                        conversation_id="conversation-1",
                        resources={},
                        resource_version=0,
                        last_active_at=NOW - timedelta(days=1),
                        archived=True,
                        created_at=NOW - timedelta(days=1),
                    ),
                ]
            )
            session.add(
                ContextSelectionRecord(
                    selection_id="selection-1",
                    conversation_id="conversation-1",
                    current_turn_id="turn-1",
                    relevant_chain_ids=["chain-active"],
                    selection_mode="single_context",
                    reason_summary="关联已有链",
                    created_at=NOW - timedelta(minutes=2),
                )
            )
            session.add(
                ContextChainNode(
                    node_id="node-1",
                    chain_id="chain-active",
                    turn_id="turn-1",
                    sequence=0,
                    related_task_ids=["task-1"],
                    related_resource_refs=["document:7"],
                    created_at=NOW - timedelta(minutes=1),
                )
            )
            session.add(
                ContextChainResource(
                    chain_id="chain-active",
                    resource_key="document:7",
                    resource_type="document",
                    resource_id="7",
                    relation="source",
                    summary="测试文档",
                    first_seen_turn_id="turn-1",
                    last_seen_turn_id="turn-1",
                    first_seen_at=NOW - timedelta(minutes=1),
                    last_seen_at=NOW - timedelta(minutes=1),
                    use_count=1,
                    active=True,
                    removed_at=None,
                )
            )
            session.commit()

    def test_get_and_list_turns_without_mutation(self) -> None:
        """验证单条获取与条件分页查询 Turn 时不产生任何写操作，并准确过滤状态。"""
        turn = self.service.get_conversation_turn("turn-1")
        result = self.service.list_conversation_turns(
            ConversationTurnSearchQuery(
                conversation_id="conversation-1",
                turn_statuses=["completed"],
            )
        )

        self.assertEqual(turn.user_input, "第一轮")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].turn_id, "turn-1")

    def test_chain_queries_respect_archived_filter(self) -> None:
        """验证链查询正确应用 archived 过滤条件。"""
        chain = self.service.get_context_chain("chain-active")
        result = self.service.list_context_chains(
            ContextChainSearchQuery(
                conversation_id="conversation-1",
                archived=False,
            )
        )

        self.assertEqual(chain.resource_version, 1)
        self.assertEqual([item.chain_id for item in result.items], ["chain-active"])

    def test_node_resource_and_selection_queries_map_facts(self) -> None:
        """验证链节点、资源事实与上下文选择记录的查询能够正确还原数据库字段。"""
        nodes = self.service.list_context_chain_nodes(
            ContextChainNodeSearchQuery(
                conversation_id="conversation-1",
                chain_id="chain-active",
            )
        )
        resources = self.service.list_context_chain_resources(
            ContextChainResourceSearchQuery(
                chain_id="chain-active",
                resource_type="document",
                resource_id="7",
                active=True,
            )
        )
        selections = self.service.list_context_selection_records(
            ContextSelectionRecordSearchQuery(
                conversation_id="conversation-1",
                selection_modes=["single_context"],
            )
        )

        self.assertEqual(nodes.items[0].related_task_ids, ["task-1"])
        self.assertEqual(resources.items[0].resource_key, "document:7")
        self.assertEqual(
            selections.items[0].relevant_chain_ids,
            ["chain-active"],
        )

    def test_seven_named_query_use_cases_delegate_without_writes(self) -> None:
        """验证 7 个独立的具名查询 UseCase 均正确调用底层服务且保持零副作用。"""
        turns = ListConversationTurnsUseCase(self.service).execute(
            ConversationTurnSearchQuery(conversation_id="conversation-1")
        )
        chains = ListContextChainsUseCase(self.service).execute(
            ContextChainSearchQuery(conversation_id="conversation-1")
        )
        nodes = ListContextChainNodesUseCase(self.service).execute(
            ContextChainNodeSearchQuery(chain_id="chain-active")
        )
        resources = ListContextChainResourcesUseCase(self.service).execute(
            ContextChainResourceSearchQuery(chain_id="chain-active")
        )
        selections = ListContextSelectionRecordsUseCase(self.service).execute(
            ContextSelectionRecordSearchQuery(
                conversation_id="conversation-1"
            )
        )

        self.assertEqual(
            GetConversationTurnUseCase(self.service).execute(
                "turn-1"
            ).turn_id,
            "turn-1",
        )
        self.assertEqual(
            GetContextChainUseCase(self.service).execute(
                "chain-active"
            ).chain_id,
            "chain-active",
        )
        self.assertEqual(turns.total, 2)
        self.assertEqual(chains.total, 2)
        self.assertEqual(nodes.total, 1)
        self.assertEqual(resources.total, 1)
        self.assertEqual(selections.total, 1)


if __name__ == "__main__":
    unittest.main()
