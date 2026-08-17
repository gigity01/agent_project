"""Context ORM Record 构造与领域模型映射。"""

from typing import Any

from app.modules.context.infrastructure.persistence.models.context_chain import (
    ContextChain as ContextChainModel,
)
from app.modules.context.infrastructure.persistence.models.context_chain_node import (
    ContextChainNode,
)
from app.modules.context.infrastructure.persistence.models.context_resource_event import (
    ContextChainResourceEvent,
)
from app.modules.context.infrastructure.persistence.models.context_selection_record import (
    ContextSelectionRecord,
)
from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn as TurnModel,
)
from app.modules.context.domain.models import (
    ContextChain,
    ContextChainNodeContext,
    ContextResourceQueue,
    ConversationTurn,
)


class SQLAlchemyContextRecordFactory:
    """隔离 Application 与 SQLAlchemy ORM 构造器。"""

    def conversation_turn(self, **values: Any) -> TurnModel:
        return TurnModel(**values)

    def context_selection_record(
        self,
        **values: Any,
    ) -> ContextSelectionRecord:
        return ContextSelectionRecord(**values)

    def context_chain(self, **values: Any) -> ContextChainModel:
        return ContextChainModel(**values)

    def context_chain_node(self, **values: Any) -> ContextChainNode:
        return ContextChainNode(**values)

    def context_resource_event(
        self,
        **values: Any,
    ) -> ContextChainResourceEvent:
        return ContextChainResourceEvent(**values)


def build_context_chain(
    chain: ContextChainModel,
    *,
    resource_queue: ContextResourceQueue,
) -> ContextChain:
    """忠实保留 Chain 中每个 Turn 的完整字段。"""
    projected_nodes: list[ContextChainNodeContext] = []

    for node in chain.nodes:
        turn = node.turn
        projected_turn = ConversationTurn(
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            user_input=turn.user_input,
            assistant_content=turn.assistant_content,
            assistant_compact=turn.assistant_compact,
            task_ids=list(turn.task_ids or []),
            task_result_summary=turn.task_result_summary,
            status=turn.status,
            created_at=turn.created_at,
            completed_at=turn.completed_at,
        )
        projected_nodes.append(
            ContextChainNodeContext(
                node_id=node.node_id,
                chain_id=node.chain_id,
                turn_id=node.turn_id,
                sequence=node.sequence,
                related_task_ids=list(node.related_task_ids or []),
                related_resource_refs=list(
                    node.related_resource_refs or []
                ),
                created_at=node.created_at,
                turn=projected_turn,
            )
        )

    return ContextChain(
        chain_id=chain.chain_id,
        conversation_id=chain.conversation_id,
        nodes=projected_nodes,
        resource_queue=resource_queue,
        last_active_at=chain.last_active_at,
        archived=chain.archived,
    )
