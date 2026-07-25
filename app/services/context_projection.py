"""将 ORM Context Chain 解析为可安全注入 Agent 的完整链视图。"""

from app.models.context_chain import ContextChain as ContextChainModel
from app.models.conversation_turn import ConversationTurn as TurnModel
from app.schemas.context import (
    ContextChain,
    ContextChainNodeContext,
    ContextResources,
    ConversationTurn,
)


def get_context_assistant_content(
    turn: TurnModel,
) -> str | None:
    """旧 Turn 优先使用压缩回答，缺少压缩结果时回退完整回答。"""
    if turn.assistant_compact:
        return turn.assistant_compact
    return turn.assistant_content


def build_context_chain(
    chain: ContextChainModel,
    *,
    full_assistant_turn_count: int,
) -> ContextChain:
    """保留全部节点，并按新旧策略选择助手回答内容。"""
    nodes = list(chain.nodes)
    full_start = max(0, len(nodes) - full_assistant_turn_count)
    projected_nodes: list[ContextChainNodeContext] = []

    for index, node in enumerate(nodes):
        turn = node.turn
        assistant_content = (
            turn.assistant_content
            if index >= full_start
            else get_context_assistant_content(turn)
        )
        projected_turn = ConversationTurn(
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            user_input=turn.user_input,
            assistant_content=assistant_content,
            assistant_compact=None,
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
        resources=ContextResources.model_validate(chain.resources or {}),
        last_active_at=chain.last_active_at,
        archived=chain.archived,
    )
