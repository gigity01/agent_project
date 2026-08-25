"""Context 持久化事实的显式只读 Use Case。"""

from app.modules.context.application.query_dto import (
    ContextChainListResult,
    ContextChainNodeListResult,
    ContextChainNodeSearchQuery,
    ContextChainQueryResult,
    ContextChainResourceListResult,
    ContextChainResourceSearchQuery,
    ContextChainSearchQuery,
    ContextSelectionRecordListResult,
    ContextSelectionRecordSearchQuery,
    ConversationTurnListResult,
    ConversationTurnQueryResult,
    ConversationTurnSearchQuery,
)
from app.modules.context.application.query_service import ContextQueryService


class GetConversationTurnUseCase:
    """读取指定 Conversation Turn 记录详情的只读用例。"""

    def __init__(self, query_service: ContextQueryService) -> None:
        self._query_service = query_service

    def execute(self, turn_id: str) -> ConversationTurnQueryResult:
        return self._query_service.get_conversation_turn(turn_id)


class ListConversationTurnsUseCase:
    """分页查询并筛选 Conversation Turn 列表的只读用例。"""

    def __init__(self, query_service: ContextQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: ConversationTurnSearchQuery,
    ) -> ConversationTurnListResult:
        return self._query_service.list_conversation_turns(query)


class GetContextChainUseCase:
    """读取指定 Context Chain 及其最新状态的只读用例。"""

    def __init__(self, query_service: ContextQueryService) -> None:
        self._query_service = query_service

    def execute(self, chain_id: str) -> ContextChainQueryResult:
        return self._query_service.get_context_chain(chain_id)


class ListContextChainsUseCase:
    def __init__(self, query_service: ContextQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: ContextChainSearchQuery,
    ) -> ContextChainListResult:
        return self._query_service.list_context_chains(query)


class ListContextChainNodesUseCase:
    def __init__(self, query_service: ContextQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: ContextChainNodeSearchQuery,
    ) -> ContextChainNodeListResult:
        return self._query_service.list_context_chain_nodes(query)


class ListContextChainResourcesUseCase:
    def __init__(self, query_service: ContextQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: ContextChainResourceSearchQuery,
    ) -> ContextChainResourceListResult:
        return self._query_service.list_context_chain_resources(query)


class ListContextSelectionRecordsUseCase:
    def __init__(self, query_service: ContextQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: ContextSelectionRecordSearchQuery,
    ) -> ContextSelectionRecordListResult:
        return self._query_service.list_context_selection_records(query)
