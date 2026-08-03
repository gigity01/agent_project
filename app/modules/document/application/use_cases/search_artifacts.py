"""文档派生产物高级查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import (
    DocumentArtifactResult,
    DocumentArtifactSearchQuery,
    SearchDocumentArtifactsResult,
)


class SearchDocumentArtifactsUseCase:
    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        query: DocumentArtifactSearchQuery,
    ) -> SearchDocumentArtifactsResult:
        with self._uow_factory() as uow:
            artifacts = uow.document_artifacts.search(query)
            return SearchDocumentArtifactsResult(
                items=[
                    DocumentArtifactResult.model_validate(artifact)
                    for artifact in artifacts
                ],
                total=uow.document_artifacts.count_search(query),
                limit=query.limit,
                offset=query.offset,
            )
