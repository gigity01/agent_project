"""Context ORM Record 工厂。"""

from typing import Any

from app.models.context_chain import ContextChain
from app.models.context_chain_node import ContextChainNode
from app.models.context_chain_resource_event import ContextChainResourceEvent
from app.models.context_route_record import ContextRouteRecord
from app.models.conversation_turn import ConversationTurn


class SQLAlchemyContextRecordFactory:
    """隔离 Application 与 SQLAlchemy ORM 构造器。"""

    def conversation_turn(self, **values: Any) -> ConversationTurn:
        return ConversationTurn(**values)

    def context_route_record(self, **values: Any) -> ContextRouteRecord:
        return ContextRouteRecord(**values)

    def context_chain(self, **values: Any) -> ContextChain:
        return ContextChain(**values)

    def context_chain_node(self, **values: Any) -> ContextChainNode:
        return ContextChainNode(**values)

    def context_resource_event(
        self,
        **values: Any,
    ) -> ContextChainResourceEvent:
        return ContextChainResourceEvent(**values)
