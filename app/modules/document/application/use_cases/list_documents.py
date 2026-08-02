"""按知识库和状态筛选文档的查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import (
    DocumentListItem,
    DocumentListQuery,
    ListDocumentsResult,
)


class ListDocumentsUseCase:
    """返回稳定分页的文档摘要列表。"""

    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, query: DocumentListQuery) -> ListDocumentsResult:
        with self._uow_factory() as uow:
            documents = uow.documents.list_filtered(
                kb_id=query.kb_id,
                status=query.status,
                source_type=query.source_type,
                lifecycle_status=query.lifecycle_status,
                limit=query.limit,
                offset=query.offset,
            )
            total = uow.documents.count_filtered(
                kb_id=query.kb_id,
                status=query.status,
                source_type=query.source_type,
                lifecycle_status=query.lifecycle_status,
            )
            return ListDocumentsResult(
                items=[
                    DocumentListItem.model_validate(document)
                    for document in documents
                ],
                total=total,
                limit=query.limit,
                offset=query.offset,
            )
