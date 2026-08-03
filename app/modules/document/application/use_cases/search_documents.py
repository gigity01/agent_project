"""文档高级条件查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import (
    DocumentListItem,
    DocumentSearchQuery,
    SearchDocumentsResult,
)


class SearchDocumentsUseCase:
    """使用白名单条件返回稳定分页的文档摘要。"""

    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, query: DocumentSearchQuery) -> SearchDocumentsResult:
        with self._uow_factory() as uow:
            documents = uow.documents.search(query)
            return SearchDocumentsResult(
                items=[
                    DocumentListItem.model_validate(document)
                    for document in documents
                ],
                total=uow.documents.count_search(query),
                limit=query.limit,
                offset=query.offset,
            )
