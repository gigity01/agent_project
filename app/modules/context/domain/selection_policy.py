"""Context Selection 结果的纯领域校验。"""

from app.modules.context.domain.enums import ContextSelectionMode
from app.modules.context.domain.models import (
    ContextChain,
    ContextSelectionDecision,
)


def derive_context_selection_mode(
    relevant_chain_ids: list[str],
) -> ContextSelectionMode:
    """由读取集合大小确定稳定模式，不把冗余分类交给模型。"""
    count = len(relevant_chain_ids)
    if count == 0:
        return ContextSelectionMode.NO_CONTEXT
    if count == 1:
        return ContextSelectionMode.SINGLE_CONTEXT
    return ContextSelectionMode.MULTI_CONTEXT


def validate_context_selection(
    decision: ContextSelectionDecision,
    chains: list[ContextChain],
    *,
    conversation_id: str,
) -> ContextSelectionDecision:
    """校验并规范化模型选择，保证每个 Chain ID 真实且可读取。"""
    chain_map: dict[str, ContextChain] = {}
    for chain in chains:
        if chain.conversation_id != conversation_id:
            raise ValueError(
                "Context chain belongs to another conversation: "
                f"{chain.chain_id}"
            )
        if chain.chain_id in chain_map:
            raise ValueError(f"Duplicate context chain: {chain.chain_id}")
        chain_map[chain.chain_id] = chain

    selected_ids = list(dict.fromkeys(decision.relevant_chain_ids))
    for chain_id in selected_ids:
        chain = chain_map.get(chain_id)
        if chain is None:
            raise ValueError(
                f"Context Agent selected unknown chain: {chain_id}"
            )
        if chain.archived:
            raise ValueError(
                f"Context Agent selected archived chain: {chain_id}"
            )

    return decision.model_copy(
        update={"relevant_chain_ids": selected_ids}
    )
