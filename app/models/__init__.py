"""集中导入 ORM 模型，确保元数据注册完整。"""

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.parent_block import ParentBlock
from app.models.child_chunk import ChildChunk
from app.models.conversation_turn import ConversationTurn
from app.models.context_chain import ContextChain
from app.models.context_chain_node import ContextChainNode
from app.models.context_chain_resource import ContextChainResource
from app.models.context_chain_resource_event import ContextChainResourceEvent
from app.models.context_route_record import ContextRouteRecord
