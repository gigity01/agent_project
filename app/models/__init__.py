"""集中导入 ORM 模型，确保元数据注册完整。"""

from app.modules.document.infrastructure.persistence.models.child_chunk import (
    ChildChunk,
)
from app.modules.document.infrastructure.persistence.models.document import Document
from app.modules.document.infrastructure.persistence.models.document_artifact import (
    DocumentArtifact,
)
from app.modules.document.infrastructure.persistence.models.knowledge_base import (
    KnowledgeBase,
)
from app.modules.document.infrastructure.persistence.models.parent_block import (
    ParentBlock,
)
from app.modules.context.infrastructure.persistence.models import (
    ContextChain,
    ContextChainNode,
    ContextChainResource,
    ContextChainResourceEvent,
    ContextRouteRecord,
    ConversationTurn,
)
