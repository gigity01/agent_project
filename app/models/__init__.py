"""集中导入 ORM 模型，确保元数据注册完整。"""

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.parent_block import ParentBlock
from app.models.child_chunk import ChildChunk
from app.modules.context.infrastructure.persistence.models import (
    ContextChain,
    ContextChainNode,
    ContextChainResource,
    ContextChainResourceEvent,
    ContextRouteRecord,
    ConversationTurn,
)
