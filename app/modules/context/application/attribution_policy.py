"""Turn Attribution 的确定性后备策略。"""

from app.modules.context.application.dto import TurnAttribution


def build_read_set_fallback_attribution(
    relevant_chain_ids: list[str],
    *,
    new_chain_id: str | None = None,
) -> TurnAttribution:
    """相关历史存在时沿用 Read Set，否则把当前 Turn 归入一条新 Chain。"""
    existing_chain_ids = list(dict.fromkeys(relevant_chain_ids))
    if existing_chain_ids:
        if new_chain_id is not None:
            raise ValueError("Existing attribution cannot preallocate a new chain")
        return TurnAttribution(existing_chain_ids=existing_chain_ids)
    return TurnAttribution(
        create_new_chain=True,
        new_chain_id=new_chain_id,
    )
