"""知识库文档与切块汇总统计用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import KnowledgeBaseStatisticsResult
from app.modules.document.application.errors import DocumentApplicationError
from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStatus,
)


class GetKnowledgeBaseStatisticsUseCase:
    """统计指定知识库内文档、生命周期、父子块与向量索引总体分布的只读用例。"""

    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, kb_id: int) -> KnowledgeBaseStatisticsResult:
        """执行统计并返回知识库级整体文档与索引统计数据。"""
        with self._uow_factory() as uow:
            knowledge_base = uow.knowledge_bases.get_by_id(kb_id)
            if knowledge_base is None:
                raise DocumentApplicationError(404, "知识库不存在")
            vector_status_counts = (
                uow.child_chunks.count_by_vector_status_for_kb(kb_id)
            )
            return KnowledgeBaseStatisticsResult(
                kb_id=knowledge_base.id,
                kb_code=knowledge_base.kb_code,
                name=knowledge_base.name,
                domain_code=knowledge_base.domain_code,
                business_scene=knowledge_base.business_scene,
                status=knowledge_base.status,
                visibility=knowledge_base.visibility,
                document_count=uow.documents.count_for_kb(kb_id),
                active_document_count=uow.documents.count_for_kb(
                    kb_id,
                    lifecycle_status=DocumentLifecycleStatus.ACTIVE.value,
                ),
                failed_document_count=uow.documents.count_for_kb(
                    kb_id,
                    status=DocumentStatus.FAILED.value,
                ),
                indexed_document_count=uow.documents.count_for_kb(
                    kb_id,
                    status=DocumentStatus.INDEXED.value,
                ),
                parent_count=uow.parent_blocks.count_active_for_kb(kb_id),
                child_count=uow.child_chunks.count_active_for_kb(kb_id),
                vector_status_counts=vector_status_counts,
            )
