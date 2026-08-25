"""Context 子系统 ORM 模型的数据库访问封装。"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.modules.context.application.query_dto import (
    ContextChainNodeSearchQuery,
    ContextChainResourceSearchQuery,
    ContextChainSearchQuery,
    ContextSelectionRecordSearchQuery,
    ConversationTurnSearchQuery,
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
from app.modules.context.infrastructure.persistence.models.context_resource_event import (
    ContextChainResourceEvent,
)
from app.modules.context.infrastructure.persistence.models.context_selection_record import (
    ContextSelectionRecord,
)
from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)


class ContextRepository:
    """集中处理 Turn、Chain、Node、Resource 与 Context Selection 事实的持久化仓储。"""

    def __init__(self, db: Session) -> None:
        """初始化 ContextRepository。

        Args:
            db: SQLAlchemy 数据库会话。
        """
        self.db = db

    def create_turn(self, turn: ConversationTurn) -> ConversationTurn:
        """创建并插入新的 ConversationTurn 记录。

        Args:
            turn: ConversationTurn ORM 实体。

        Returns:
            ConversationTurn: 持久化并刷新后的实体。
        """
        self.db.add(turn)
        self.db.flush()
        self.db.refresh(turn)
        return turn

    def get_turn(self, turn_id: str) -> ConversationTurn | None:
        """根据 turn_id 查询 Turn（无锁）。

        Args:
            turn_id: Turn ID。

        Returns:
            ConversationTurn | None: 命中的实体或 None。
        """
        return (
            self.db.query(ConversationTurn)
            .filter(ConversationTurn.turn_id == turn_id)
            .first()
        )

    def search_turns(
        self,
        filters: ConversationTurnSearchQuery,
    ) -> list[ConversationTurn]:
        """分页筛选查询 ConversationTurn 列表。

        Args:
            filters: 过滤与分页参数。

        Returns:
            list[ConversationTurn]: 命中的实体列表。
        """
        return (
            self._turn_search_query(filters)
            .order_by(
                ConversationTurn.created_at.desc(),
                ConversationTurn.turn_id.desc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )

    def count_turns(self, filters: ConversationTurnSearchQuery) -> int:
        """统计符合条件的 ConversationTurn 总数。

        Args:
            filters: 过滤参数。

        Returns:
            int: 匹配记录数。
        """
        return self._turn_search_query(filters).count()

    def _turn_search_query(self, filters: ConversationTurnSearchQuery):
        """构建 ConversationTurn 动态查询 Query。"""
        query = self.db.query(ConversationTurn)
        if filters.conversation_id is not None:
            query = query.filter(
                ConversationTurn.conversation_id == filters.conversation_id
            )
        if filters.turn_ids:
            query = query.filter(ConversationTurn.turn_id.in_(filters.turn_ids))
        if filters.turn_statuses:
            query = query.filter(
                ConversationTurn.status.in_(filters.turn_statuses)
            )
        if filters.created_from is not None:
            query = query.filter(
                ConversationTurn.created_at >= filters.created_from
            )
        if filters.created_to is not None:
            query = query.filter(
                ConversationTurn.created_at <= filters.created_to
            )
        if filters.completed_from is not None:
            query = query.filter(
                ConversationTurn.completed_at >= filters.completed_from
            )
        if filters.completed_to is not None:
            query = query.filter(
                ConversationTurn.completed_at <= filters.completed_to
            )
        return query

    def get_turn_for_update(self, turn_id: str) -> ConversationTurn | None:
        """根据 turn_id 获取带行级排他锁的 Turn 实体。

        Args:
            turn_id: Turn ID。

        Returns:
            ConversationTurn | None: 锁定的实体或 None。
        """
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
        """更新 Turn 状态并 flush。

        Args:
            turn: ConversationTurn 实体。
            status: 新状态字符串。

        Returns:
            ConversationTurn: 更新后的实体。
        """
        turn.status = status
        self.db.flush()
        return turn

    def list_active_chains(self, conversation_id: str) -> list[ContextChain]:
        """加载当前 Conversation 的全部未归档完整链（预加载节点与 Turn）。

        Args:
            conversation_id: 会话 ID。

        Returns:
            list[ContextChain]: 未归档上下文链列表（按 last_active_at 倒序排列）。
        """
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
        """根据链 ID 集合锁定并查询 ContextChain 列表（带行级排他锁）。

        Args:
            chain_ids: 上下文链 ID 迭代器。

        Returns:
            list[ContextChain]: 锁定的链实体列表。
        """
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

    def get_chains_by_ids(
        self,
        chain_ids: Iterable[str],
    ) -> list[ContextChain]:
        """按 ID 加载完整 Chain 及其关联节点，不改变业务活跃时间。

        Args:
            chain_ids: 上下文链 ID 迭代器。

        Returns:
            list[ContextChain]: 链实体列表。
        """
        ordered_ids = sorted(set(chain_ids))
        if not ordered_ids:
            return []
        return (
            self.db.query(ContextChain)
            .options(
                selectinload(ContextChain.nodes).selectinload(
                    ContextChainNode.turn
                )
            )
            .filter(ContextChain.chain_id.in_(ordered_ids))
            .order_by(ContextChain.chain_id.asc())
            .all()
        )

    def get_chain(self, chain_id: str) -> ContextChain | None:
        """根据 chain_id 查询 ContextChain。

        Args:
            chain_id: 上下文链 ID。

        Returns:
            ContextChain | None: 命中的链或 None。
        """
        return (
            self.db.query(ContextChain)
            .filter(ContextChain.chain_id == chain_id)
            .first()
        )

    def search_chains(
        self,
        filters: ContextChainSearchQuery,
    ) -> list[ContextChain]:
        """分页筛选查询 ContextChain 列表。

        Args:
            filters: 过滤与分页参数。

        Returns:
            list[ContextChain]: 命中的链实体列表。
        """
        return (
            self._chain_search_query(filters)
            .order_by(
                ContextChain.last_active_at.desc(),
                ContextChain.chain_id.asc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )

    def count_chains(self, filters: ContextChainSearchQuery) -> int:
        """统计符合条件的 ContextChain 总数。

        Args:
            filters: 过滤参数。

        Returns:
            int: 匹配记录数。
        """
        return self._chain_search_query(filters).count()

    def _chain_search_query(self, filters: ContextChainSearchQuery):
        """构建 ContextChain 动态查询 Query。"""
        query = self.db.query(ContextChain)
        if filters.conversation_id is not None:
            query = query.filter(
                ContextChain.conversation_id == filters.conversation_id
            )
        if filters.chain_ids:
            query = query.filter(ContextChain.chain_id.in_(filters.chain_ids))
        if filters.archived is not None:
            query = query.filter(ContextChain.archived.is_(filters.archived))
        if filters.created_from is not None:
            query = query.filter(ContextChain.created_at >= filters.created_from)
        if filters.created_to is not None:
            query = query.filter(ContextChain.created_at <= filters.created_to)
        return query

    def get_chain_for_update(self, chain_id: str) -> ContextChain | None:
        """根据 chain_id 获取带行锁的 ContextChain。

        Args:
            chain_id: 上下文链 ID。

        Returns:
            ContextChain | None: 锁定的实体或 None。
        """
        return (
            self.db.query(ContextChain)
            .filter(ContextChain.chain_id == chain_id)
            .with_for_update()
            .first()
        )

    def create_chain(self, chain: ContextChain) -> ContextChain:
        """创建并插入新的 ContextChain。

        Args:
            chain: ContextChain ORM 实体。

        Returns:
            ContextChain: 实体实例。
        """
        self.db.add(chain)
        self.db.flush()
        return chain

    def create_selection_record(
        self,
        selection_record: ContextSelectionRecord,
    ) -> ContextSelectionRecord:
        """创建并插入 ContextSelectionRecord 路由决策记录。

        Args:
            selection_record: ContextSelectionRecord ORM 实体。

        Returns:
            ContextSelectionRecord: 实体实例。
        """
        self.db.add(selection_record)
        self.db.flush()
        return selection_record

    def get_selection_record_for_update(
        self,
        turn_id: str,
    ) -> ContextSelectionRecord | None:
        """根据 turn_id 锁定并查询对应的 ContextSelectionRecord。

        Args:
            turn_id: Turn ID。

        Returns:
            ContextSelectionRecord | None: 锁定的实体或 None。
        """
        return (
            self.db.query(ContextSelectionRecord)
            .filter(ContextSelectionRecord.current_turn_id == turn_id)
            .with_for_update()
            .first()
        )

    def get_selection_record(
        self,
        turn_id: str,
    ) -> ContextSelectionRecord | None:
        """根据 turn_id 查询对应的 ContextSelectionRecord（无锁）。

        Args:
            turn_id: Turn ID。

        Returns:
            ContextSelectionRecord | None: 命中的实体或 None。
        """
        return (
            self.db.query(ContextSelectionRecord)
            .filter(ContextSelectionRecord.current_turn_id == turn_id)
            .first()
        )

    def get_node(
        self,
        chain_id: str,
        turn_id: str,
    ) -> ContextChainNode | None:
        """根据 chain_id 和 turn_id 查询对应的 ContextChainNode。

        Args:
            chain_id: 上下文链 ID。
            turn_id: Turn ID。

        Returns:
            ContextChainNode | None: 命中的实体或 None。
        """
        return (
            self.db.query(ContextChainNode)
            .filter(
                ContextChainNode.chain_id == chain_id,
                ContextChainNode.turn_id == turn_id,
            )
            .first()
        )

    def search_nodes(
        self,
        filters: ContextChainNodeSearchQuery,
    ) -> list[ContextChainNode]:
        """分页筛选查询 ContextChainNode 列表。

        Args:
            filters: 过滤与分页参数。

        Returns:
            list[ContextChainNode]: 命中的节点实体列表。
        """
        return (
            self._node_search_query(filters)
            .order_by(
                ContextChainNode.chain_id.asc(),
                ContextChainNode.sequence.asc(),
                ContextChainNode.node_id.asc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )

    def count_nodes(self, filters: ContextChainNodeSearchQuery) -> int:
        """统计符合条件的 ContextChainNode 总数。

        Args:
            filters: 过滤参数。

        Returns:
            int: 匹配记录数。
        """
        return self._node_search_query(filters).count()

    def _node_search_query(self, filters: ContextChainNodeSearchQuery):
        """构建 ContextChainNode 动态查询 Query。"""
        query = self.db.query(ContextChainNode)
        if filters.conversation_id is not None:
            query = query.join(
                ContextChain,
                ContextChain.chain_id == ContextChainNode.chain_id,
            ).filter(
                ContextChain.conversation_id == filters.conversation_id
            )
        if filters.chain_id is not None:
            query = query.filter(ContextChainNode.chain_id == filters.chain_id)
        if filters.chain_ids:
            query = query.filter(
                ContextChainNode.chain_id.in_(filters.chain_ids)
            )
        if filters.turn_id is not None:
            query = query.filter(ContextChainNode.turn_id == filters.turn_id)
        if filters.turn_ids:
            query = query.filter(
                ContextChainNode.turn_id.in_(filters.turn_ids)
            )
        if filters.created_from is not None:
            query = query.filter(
                ContextChainNode.created_at >= filters.created_from
            )
        if filters.created_to is not None:
            query = query.filter(
                ContextChainNode.created_at <= filters.created_to
            )
        return query

    def get_next_sequence(self, chain_id: str) -> int:
        """获取指定链下一个递增的节点序号 sequence（从 0 开始）。

        Args:
            chain_id: 上下文链 ID。

        Returns:
            int: 下一个 sequence 序号。
        """
        current = (
            self.db.query(func.max(ContextChainNode.sequence))
            .filter(ContextChainNode.chain_id == chain_id)
            .scalar()
        )
        return 0 if current is None else current + 1

    def create_node(self, node: ContextChainNode) -> ContextChainNode:
        """创建并插入新的 ContextChainNode。

        Args:
            node: ContextChainNode ORM 实体。

        Returns:
            ContextChainNode: 实体实例。
        """
        self.db.add(node)
        self.db.flush()
        return node

    def get_chain_resource_for_update(
        self,
        chain_id: str,
        resource_key: str,
    ) -> ContextChainResource | None:
        """根据 (chain_id, resource_key) 锁定并获取资源当前状态记录。

        Args:
            chain_id: 上下文链 ID。
            resource_key: 资源规范 Key。

        Returns:
            ContextChainResource | None: 锁定的实体或 None。
        """
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
        """刷新资源当前状态，返回资源记录以及是否为首次出现。

        Args:
            chain_id: 上下文链 ID。
            resource_key: 资源规范 Key。
            resource_type: 资源类型。
            resource_id: 资源业务标识。
            relation: 关系描述。
            summary: 简要摘要。
            turn_id: 当前关联 Turn ID。
            seen_at: 活跃时间戳。

        Returns:
            tuple[ContextChainResource, bool]: (resource_entity, created_bool)。
        """
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
        """将资源标记为失效（active=False）；历史记录和最后使用信息继续保留。

        Args:
            chain_id: 上下文链 ID。
            resource_key: 资源规范 Key。
            removed_at: 移除时间戳。

        Returns:
            ContextChainResource | None: 更新后的实体或 None。
        """
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
        """插入一条不可变的 ContextChainResourceEvent 资源历史事件。

        Args:
            event: ContextChainResourceEvent ORM 实体。

        Returns:
            ContextChainResourceEvent: 实体实例。
        """
        self.db.add(event)
        self.db.flush()
        return event

    def list_resources_for_warmup(
        self,
        chain_id: str,
        *,
        limit: int,
    ) -> list[ContextChainResource]:
        """按最近到最旧返回活跃资源（active=True），供应用服务反转为 FIFO 顺序。

        Args:
            chain_id: 上下文链 ID。
            limit: 数量限制。

        Returns:
            list[ContextChainResource]: 最近活跃资源列表。
        """
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

    def search_resources(
        self,
        filters: ContextChainResourceSearchQuery,
    ) -> list[ContextChainResource]:
        """分页筛选查询 ContextChainResource 列表。

        Args:
            filters: 过滤与分页参数。

        Returns:
            list[ContextChainResource]: 命中的资源实体列表。
        """
        return (
            self._resource_search_query(filters)
            .order_by(
                ContextChainResource.last_seen_at.desc(),
                ContextChainResource.id.desc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )

    def count_resources(
        self,
        filters: ContextChainResourceSearchQuery,
    ) -> int:
        """统计符合条件的 ContextChainResource 总数。

        Args:
            filters: 过滤参数。

        Returns:
            int: 匹配记录数。
        """
        return self._resource_search_query(filters).count()

    def _resource_search_query(
        self,
        filters: ContextChainResourceSearchQuery,
    ):
        """构建 ContextChainResource 动态查询 Query。"""
        query = self.db.query(ContextChainResource)
        if filters.conversation_id is not None:
            query = query.join(
                ContextChain,
                ContextChain.chain_id == ContextChainResource.chain_id,
            ).filter(
                ContextChain.conversation_id == filters.conversation_id
            )
        if filters.chain_id is not None:
            query = query.filter(
                ContextChainResource.chain_id == filters.chain_id
            )
        if filters.chain_ids:
            query = query.filter(
                ContextChainResource.chain_id.in_(filters.chain_ids)
            )
        if filters.resource_type is not None:
            query = query.filter(
                ContextChainResource.resource_type == filters.resource_type
            )
        if filters.resource_id is not None:
            query = query.filter(
                ContextChainResource.resource_id == filters.resource_id
            )
        if filters.active is not None:
            query = query.filter(
                ContextChainResource.active.is_(filters.active)
            )
        if filters.last_seen_from is not None:
            query = query.filter(
                ContextChainResource.last_seen_at >= filters.last_seen_from
            )
        if filters.last_seen_to is not None:
            query = query.filter(
                ContextChainResource.last_seen_at <= filters.last_seen_to
            )
        return query

    def search_selection_records(
        self,
        filters: ContextSelectionRecordSearchQuery,
    ) -> list[ContextSelectionRecord]:
        """分页筛选查询 ContextSelectionRecord 列表。

        Args:
            filters: 过滤与分页参数。

        Returns:
            list[ContextSelectionRecord]: 命中的选择记录实体列表。
        """
        return (
            self._selection_record_search_query(filters)
            .order_by(
                ContextSelectionRecord.created_at.desc(),
                ContextSelectionRecord.selection_id.desc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )

    def count_selection_records(
        self,
        filters: ContextSelectionRecordSearchQuery,
    ) -> int:
        """统计符合条件的 ContextSelectionRecord 总数。

        Args:
            filters: 过滤参数。

        Returns:
            int: 匹配记录数。
        """
        return self._selection_record_search_query(filters).count()

    def _selection_record_search_query(
        self,
        filters: ContextSelectionRecordSearchQuery,
    ):
        """构建 ContextSelectionRecord 动态查询 Query。"""
        query = self.db.query(ContextSelectionRecord)
        if filters.conversation_id is not None:
            query = query.filter(
                ContextSelectionRecord.conversation_id
                == filters.conversation_id
            )
        if filters.turn_id is not None:
            query = query.filter(
                ContextSelectionRecord.current_turn_id == filters.turn_id
            )
        if filters.selection_modes:
            query = query.filter(
                ContextSelectionRecord.selection_mode.in_(
                    filters.selection_modes
                )
            )
        if filters.created_from is not None:
            query = query.filter(
                ContextSelectionRecord.created_at >= filters.created_from
            )
        if filters.created_to is not None:
            query = query.filter(
                ContextSelectionRecord.created_at <= filters.created_to
            )
        return query

    def increment_resource_version(
        self,
        chain: ContextChain,
    ) -> int:
        """将 ContextChain 的 resource_version 单调递增 1 并 flush。

        Args:
            chain: ContextChain 实体。

        Returns:
            int: 递增后的新版本号。
        """
        chain.resource_version += 1
        self.db.flush()
        return chain.resource_version

    def list_linked_chain_ids(self, turn_id: str) -> list[str]:
        """查询指定 Turn 已关联建立节点的所有 ContextChain ID 列表。

        Args:
            turn_id: Turn ID。

        Returns:
            list[str]: 关联的链 ID 列表。
        """
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
        """回写完成字段并更新 Turn 终态。

        Args:
            turn: ConversationTurn 实体。
            assistant_content: 助手完整文本。
            assistant_compact: 紧凑摘要。
            task_ids: 关联任务 ID 列表。
            task_result_summary: 任务结果摘要。
            completed_at: 完成时间戳。
            status: 终态状态字符串（COMPLETED）。

        Returns:
            ConversationTurn: 更新后的实体。
        """
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
        """更新上下文链的最后活跃时间并确保 archived 为 False。

        Args:
            chain: ContextChain 实体。
            last_active_at: 活跃时间戳。

        Returns:
            ContextChain: 更新后的实体。
        """
        chain.last_active_at = last_active_at
        chain.archived = False
        self.db.flush()
        return chain
