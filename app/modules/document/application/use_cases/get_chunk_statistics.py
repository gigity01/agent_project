"""文档父子块与向量状态统计用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import DocumentChunkStatisticsResult
from app.modules.document.application.errors import DocumentApplicationError


class GetDocumentChunkStatisticsUseCase:
    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: int) -> DocumentChunkStatisticsResult:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id)
            if document is None:
                raise DocumentApplicationError(404, "文档不存在")
            parent_status_counts = (
                uow.parent_blocks.count_by_status_for_document(document_id)
            )
            child_status_counts = (
                uow.child_chunks.count_by_status_for_document(document_id)
            )
            vector_status_counts = (
                uow.child_chunks.count_all_by_vector_status_for_document(
                    document_id
                )
            )
            chunks_with_vector_id, chunks_without_vector_id = (
                uow.child_chunks.count_vector_id_presence_for_document(
                    document_id
                )
            )
            return DocumentChunkStatisticsResult(
                document_id=document.id,
                doc_code=document.doc_code,
                parent_count=sum(parent_status_counts.values()),
                child_count=sum(child_status_counts.values()),
                parent_status_counts=parent_status_counts,
                child_status_counts=child_status_counts,
                vector_status_counts=vector_status_counts,
                chunk_type_counts=(
                    uow.child_chunks.count_by_chunk_type_for_document(
                        document_id
                    )
                ),
                chunks_with_vector_id=chunks_with_vector_id,
                chunks_without_vector_id=chunks_without_vector_id,
            )
