"""Context 子系统 ORM 模型的数据库访问封装。"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.context_chain import ContextChain
from app.models.context_chain_node import ContextChainNode
from app.models.context_route_record import ContextRouteRecord
from app.models.conversation_turn import ConversationTurn


class ContextRepository:
    """集中处理 Turn、Chain、Node 和路由决策的持久化。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_turn(self, turn: ConversationTurn) -> ConversationTurn:
        self.db.add(turn)
        self.db.flush()
        self.db.refresh(turn)
        return turn

    def get_turn(self, turn_id: str) -> ConversationTurn | None:
        return (
            self.db.query(ConversationTurn)
            .filter(ConversationTurn.turn_id == turn_id)
            .first()
        )

    def get_turn_for_update(self, turn_id: str) -> ConversationTurn | None:
        return (
            self.db.query(ConversationTurn)
            .filter(ConversationTurn.turn_id == turn_id)
            .with_for_update()
            .first()
        )

    def set_turn_status(
        self,
        turn: ConversationTurn,
        status: str,
    ) -> ConversationTurn:
        turn.status = status
        self.db.flush()
        return turn

    def list_active_chains(self, conversation_id: str) -> list[ContextChain]:
        """加载当前 Conversation 的全部未归档完整链。"""
        return (
            self.db.query(ContextChain)
            .options(
                selectinload(ContextChain.nodes).selectinload(
                    ContextChainNode.turn
                )
            )
            .filter(
                ContextChain.conversation_id == conversation_id,
                ContextChain.archived.is_(False),
            )
            .order_by(
                ContextChain.last_active_at.desc(),
                ContextChain.chain_id.asc(),
            )
            .all()
        )

    def get_chains_by_ids_for_update(
        self,
        chain_ids: Iterable[str],
    ) -> list[ContextChain]:
        ordered_ids = sorted(set(chain_ids))
        if not ordered_ids:
            return []

        return (
            self.db.query(ContextChain)
            .filter(ContextChain.chain_id.in_(ordered_ids))
            .order_by(ContextChain.chain_id.asc())
            .with_for_update()
            .all()
        )

    def get_chain_for_update(self, chain_id: str) -> ContextChain | None:
        return (
            self.db.query(ContextChain)
            .filter(ContextChain.chain_id == chain_id)
            .with_for_update()
            .first()
        )

    def create_chain(self, chain: ContextChain) -> ContextChain:
        self.db.add(chain)
        self.db.flush()
        return chain

    def create_route_record(
        self,
        route_record: ContextRouteRecord,
    ) -> ContextRouteRecord:
        self.db.add(route_record)
        self.db.flush()
        return route_record

    def get_route_record_for_update(
        self,
        turn_id: str,
    ) -> ContextRouteRecord | None:
        return (
            self.db.query(ContextRouteRecord)
            .filter(ContextRouteRecord.current_turn_id == turn_id)
            .with_for_update()
            .first()
        )

    def get_node(
        self,
        chain_id: str,
        turn_id: str,
    ) -> ContextChainNode | None:
        return (
            self.db.query(ContextChainNode)
            .filter(
                ContextChainNode.chain_id == chain_id,
                ContextChainNode.turn_id == turn_id,
            )
            .first()
        )

    def get_next_sequence(self, chain_id: str) -> int:
        current = (
            self.db.query(func.max(ContextChainNode.sequence))
            .filter(ContextChainNode.chain_id == chain_id)
            .scalar()
        )
        return 0 if current is None else current + 1

    def create_node(self, node: ContextChainNode) -> ContextChainNode:
        self.db.add(node)
        self.db.flush()
        return node

    def list_linked_chain_ids(self, turn_id: str) -> list[str]:
        rows = (
            self.db.query(ContextChainNode.chain_id)
            .filter(ContextChainNode.turn_id == turn_id)
            .order_by(ContextChainNode.chain_id.asc())
            .all()
        )
        return [row[0] for row in rows]

    def complete_turn(
        self,
        turn: ConversationTurn,
        *,
        assistant_content: str | None,
        assistant_compact: str | None,
        task_ids: list[str],
        task_result_summary: str | None,
        completed_at: datetime,
        status: str,
    ) -> ConversationTurn:
        turn.assistant_content = assistant_content
        turn.assistant_compact = assistant_compact
        turn.task_ids = task_ids
        turn.task_result_summary = task_result_summary
        turn.completed_at = completed_at
        turn.status = status
        self.db.flush()
        return turn

    def update_chain_activity(
        self,
        chain: ContextChain,
        *,
        last_active_at: datetime,
        resources: dict | None = None,
    ) -> ContextChain:
        if resources is not None:
            chain.resources = resources
        chain.last_active_at = last_active_at
        chain.archived = False
        self.db.flush()
        return chain
