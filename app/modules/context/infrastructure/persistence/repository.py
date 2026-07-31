"""Context 子系统 ORM 模型的数据库访问封装。"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.context_chain import ContextChain
from app.models.context_chain_node import ContextChainNode
from app.models.context_chain_resource import ContextChainResource
from app.models.context_chain_resource_event import (
    ContextChainResourceEvent,
)
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

    def get_chain(self, chain_id: str) -> ContextChain | None:
        return (
            self.db.query(ContextChain)
            .filter(ContextChain.chain_id == chain_id)
            .first()
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

    def get_chain_resource_for_update(
        self,
        chain_id: str,
        resource_key: str,
    ) -> ContextChainResource | None:
        return (
            self.db.query(ContextChainResource)
            .filter(
                ContextChainResource.chain_id == chain_id,
                ContextChainResource.resource_key == resource_key,
            )
            .with_for_update()
            .first()
        )

    def upsert_chain_resource(
        self,
        *,
        chain_id: str,
        resource_key: str,
        resource_type: str,
        resource_id: str,
        relation: str | None,
        summary: str | None,
        turn_id: str,
        seen_at: datetime,
    ) -> tuple[ContextChainResource, bool]:
        """刷新资源当前状态，返回资源记录以及是否为首次出现。"""
        resource = self.get_chain_resource_for_update(
            chain_id,
            resource_key,
        )
        created = resource is None
        if resource is None:
            resource = ContextChainResource(
                chain_id=chain_id,
                resource_key=resource_key,
                resource_type=resource_type,
                resource_id=resource_id,
                relation=relation,
                summary=summary,
                first_seen_turn_id=turn_id,
                last_seen_turn_id=turn_id,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                use_count=1,
                active=True,
                removed_at=None,
            )
            self.db.add(resource)
        else:
            resource.resource_type = resource_type
            resource.resource_id = resource_id
            resource.relation = relation
            resource.summary = summary
            resource.last_seen_turn_id = turn_id
            resource.last_seen_at = seen_at
            resource.use_count += 1
            resource.active = True
            resource.removed_at = None

        self.db.flush()
        return resource, created

    def deactivate_chain_resource(
        self,
        *,
        chain_id: str,
        resource_key: str,
        removed_at: datetime,
    ) -> ContextChainResource | None:
        """将资源标记为失效；历史记录和最后使用信息继续保留。"""
        resource = self.get_chain_resource_for_update(
            chain_id,
            resource_key,
        )
        if resource is None:
            return None

        resource.active = False
        resource.removed_at = removed_at
        self.db.flush()
        return resource

    def create_resource_event(
        self,
        event: ContextChainResourceEvent,
    ) -> ContextChainResourceEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def list_resources_for_warmup(
        self,
        chain_id: str,
        *,
        limit: int,
    ) -> list[ContextChainResource]:
        """按最近到最旧返回活跃资源，由 Service 反转为 FIFO 顺序。"""
        return (
            self.db.query(ContextChainResource)
            .filter(
                ContextChainResource.chain_id == chain_id,
                ContextChainResource.active.is_(True),
            )
            .order_by(
                ContextChainResource.last_seen_at.desc(),
                ContextChainResource.resource_key.desc(),
            )
            .limit(limit)
            .all()
        )

    def increment_resource_version(
        self,
        chain: ContextChain,
    ) -> int:
        chain.resource_version += 1
        self.db.flush()
        return chain.resource_version

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
    ) -> ContextChain:
        chain.last_active_at = last_active_at
        chain.archived = False
        self.db.flush()
        return chain
