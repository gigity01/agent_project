"""Context 持久化事实的只读查询服务。"""

from __future__ import annotations

from app.modules.context.application.errors import ContextQueryError
from app.modules.context.application.ports import UnitOfWorkFactory
from app.modules.context.application.query_dto import (
    ContextChainListResult,
    ContextChainNodeListResult,
    ContextChainNodeQueryResult,
    ContextChainNodeSearchQuery,
    ContextChainQueryResult,
    ContextChainResourceListResult,
    ContextChainResourceQueryResult,
    ContextChainResourceSearchQuery,
    ContextChainSearchQuery,
    ContextSelectionRecordListResult,
    ContextSelectionRecordQueryResult,
    ContextSelectionRecordSearchQuery,
    ConversationTurnListResult,
    ConversationTurnQueryResult,
    ConversationTurnSearchQuery,
)


class ContextQueryService:
    """提供不改变 Chain 活跃时间或资源版本的查询能力。"""

    def __init__(self, *, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def get_conversation_turn(
        self,
        turn_id: str,
    ) -> ConversationTurnQueryResult:
        with self._uow_factory() as uow:
            turn = uow.context.get_turn(turn_id)
            if turn is None:
                raise ContextQueryError(404, "Context Turn 不存在")
            return ConversationTurnQueryResult.model_validate(turn)

    def list_conversation_turns(
        self,
        query: ConversationTurnSearchQuery,
    ) -> ConversationTurnListResult:
        with self._uow_factory() as uow:
            items = uow.context.search_turns(query)
            return ConversationTurnListResult(
                items=[
                    ConversationTurnQueryResult.model_validate(item)
                    for item in items
                ],
                total=uow.context.count_turns(query),
                limit=query.limit,
                offset=query.offset,
            )

    def get_context_chain(self, chain_id: str) -> ContextChainQueryResult:
        with self._uow_factory() as uow:
            chain = uow.context.get_chain(chain_id)
            if chain is None:
                raise ContextQueryError(404, "Context Chain 不存在")
            return ContextChainQueryResult.model_validate(chain)

    def list_context_chains(
        self,
        query: ContextChainSearchQuery,
    ) -> ContextChainListResult:
        with self._uow_factory() as uow:
            items = uow.context.search_chains(query)
            return ContextChainListResult(
                items=[
                    ContextChainQueryResult.model_validate(item)
                    for item in items
                ],
                total=uow.context.count_chains(query),
                limit=query.limit,
                offset=query.offset,
            )

    def list_context_chain_nodes(
        self,
        query: ContextChainNodeSearchQuery,
    ) -> ContextChainNodeListResult:
        with self._uow_factory() as uow:
            items = uow.context.search_nodes(query)
            return ContextChainNodeListResult(
                items=[
                    ContextChainNodeQueryResult.model_validate(item)
                    for item in items
                ],
                total=uow.context.count_nodes(query),
                limit=query.limit,
                offset=query.offset,
            )

    def list_context_chain_resources(
        self,
        query: ContextChainResourceSearchQuery,
    ) -> ContextChainResourceListResult:
        with self._uow_factory() as uow:
            items = uow.context.search_resources(query)
            return ContextChainResourceListResult(
                items=[
                    ContextChainResourceQueryResult.model_validate(item)
                    for item in items
                ],
                total=uow.context.count_resources(query),
                limit=query.limit,
                offset=query.offset,
            )

    def list_context_selection_records(
        self,
        query: ContextSelectionRecordSearchQuery,
    ) -> ContextSelectionRecordListResult:
        with self._uow_factory() as uow:
            items = uow.context.search_selection_records(query)
            return ContextSelectionRecordListResult(
                items=[
                    ContextSelectionRecordQueryResult.model_validate(item)
                    for item in items
                ],
                total=uow.context.count_selection_records(query),
                limit=query.limit,
                offset=query.offset,
            )
