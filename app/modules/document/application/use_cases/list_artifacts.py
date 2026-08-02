"""列出文档派生产物的查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import (
    DocumentArtifactResult,
    ListDocumentArtifactsResult,
)
from app.modules.document.application.errors import DocumentApplicationError


class ListDocumentArtifactsUseCase:
    """通过应用层返回指定文档的产物元数据。"""

    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: int) -> ListDocumentArtifactsResult:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id)
            if document is None:
                raise DocumentApplicationError(404, "文档不存在")

            artifacts = uow.document_artifacts.list_by_document_id(
                document_id
            )
            return ListDocumentArtifactsResult(
                document_id=document_id,
                source_uri=document.source_uri,
                source_type=document.source_type,
                original_filename=document.original_filename,
                items=[
                    DocumentArtifactResult.model_validate(artifact)
                    for artifact in artifacts
                ],
            )
