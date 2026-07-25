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
    from app.models.context_chain import ContextChain as ContextChainModel
    from app.models.context_chain_node import (
        ContextChainNode as ContextChainNodeModel,
    )
    from app.models.context_route_record import ContextRouteRecord
    from app.models.conversation_turn import (
        ConversationTurn as ConversationTurnModel,
    )
    from app.schemas.context import (
        CompleteContextTurnRequest,
        ContextChain,
        ContextChainTurnUpdate,
        ContextResources,
        ContextRouteDecision,
        ContextRouteMode,
        ContextRouteRequest,
    )
    from app.services.context_route_validation import (
        validate_route_decision,
    )
    from app.services.context_service import ContextService


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
        resources=ContextResources(),
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
                ContextRouteRecord.__table__,
            ],
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.lock_manager = _RouteLockManager()
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
            uow_factory=lambda: SQLAlchemyUnitOfWork(
                self.session_factory
            ),
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
                        related_resource_refs=["result-1"],
                        resources=ContextResources(
                            task_ids=["task-1"],
                            result_refs=["result-1"],
                        ),
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

        self.assertEqual(len(turns), 1)
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].turn_id, turns[0].turn_id)
        self.assertEqual(nodes[0].chain_id, chains[0].chain_id)
        self.assertEqual(nodes[0].related_task_ids, ["task-1"])
        self.assertEqual(chains[0].resources["result_refs"], ["result-1"])
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


if __name__ == "__main__":
    unittest.main()
