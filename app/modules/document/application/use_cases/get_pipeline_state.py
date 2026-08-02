"""读取文档处理、切块和索引进度的查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import DocumentPipelineStateResult
from app.modules.document.application.errors import DocumentApplicationError


class GetDocumentPipelineStateUseCase:
    """汇总文档状态轴以及父子块计数。"""

    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: int) -> DocumentPipelineStateResult:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id)
            if document is None:
                raise DocumentApplicationError(404, "文档不存在")

            vector_status_counts = (
                uow.child_chunks.count_by_vector_status_for_document(
                    document_id
                )
            )
            return DocumentPipelineStateResult(
                document_id=document.id,
                doc_code=document.doc_code,
                source_type=document.source_type,
                source_uri=document.source_uri,
                cleaned_uri=document.cleaned_uri,
                document_status=document.status,
                lifecycle_status=document.lifecycle_status,
                storage_status=document.storage_status,
                parent_count=(
                    uow.parent_blocks.count_active_by_doc_id(document_id)
                ),
                child_count=sum(vector_status_counts.values()),
                vector_status_counts=vector_status_counts,
                indexed_at=document.indexed_at,
            )
