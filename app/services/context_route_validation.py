"""Context Agent 路由结果的确定性校验。"""

from app.schemas.context import (
    ContextChain,
    ContextRouteDecision,
    ContextRouteMode,
)


def validate_route_decision(
    decision: ContextRouteDecision,
    chains: list[ContextChain],
    *,
    conversation_id: str,
) -> ContextRouteDecision:
    """校验并规范化模型输出，保证链身份和 mode/字段组合合法。"""
    chain_map: dict[str, ContextChain] = {}
    for chain in chains:
        if chain.conversation_id != conversation_id:
            raise ValueError(
                f"Context chain belongs to another conversation: {chain.chain_id}"
            )
        if chain.chain_id in chain_map:
            raise ValueError(f"Duplicate context chain: {chain.chain_id}")
        chain_map[chain.chain_id] = chain

    selected_ids = list(dict.fromkeys(decision.selected_chain_ids))
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

    mode = decision.route_mode
    create_new_chain = decision.create_new_chain

    if mode == ContextRouteMode.FALLBACK_LATEST:
        active_chains = [chain for chain in chains if not chain.archived]
        if not active_chains:
            raise ValueError("fallback_latest requires an active chain")
        latest_chain = max(
            active_chains,
            key=lambda item: (item.last_active_at, item.chain_id),
        )
        selected_ids = [latest_chain.chain_id]
        create_new_chain = False
    elif mode == ContextRouteMode.NEW_CHAIN:
        selected_ids = []
        create_new_chain = True
    elif mode == ContextRouteMode.SINGLE_MATCH:
        if len(selected_ids) != 1 or create_new_chain:
            raise ValueError("single_match requires exactly one existing chain")
        create_new_chain = False
    elif mode == ContextRouteMode.MULTI_MATCH:
        if len(selected_ids) < 2 or create_new_chain:
            raise ValueError("multi_match requires at least two existing chains")
        create_new_chain = False
    elif mode == ContextRouteMode.EXISTING_AND_NEW:
        if not selected_ids or not create_new_chain:
            raise ValueError(
                "existing_and_new requires existing chains and a new chain"
            )
        create_new_chain = True
    else:
        raise ValueError(f"Unsupported context route mode: {mode}")

    return decision.model_copy(
        update={
            "selected_chain_ids": selected_ids,
            "create_new_chain": create_new_chain,
        }
    )
