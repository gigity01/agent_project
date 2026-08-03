"""可向量化子块条件查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import (
    ChildChunkResult,
    ChildChunkSearchQuery,
    ListChildChunksResult,
)


class ListChildChunksUseCase:
    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, query: ChildChunkSearchQuery) -> ListChildChunksResult:
        with self._uow_factory() as uow:
            chunks = uow.child_chunks.search(query)
            return ListChildChunksResult(
                items=[
                    ChildChunkResult.model_validate(chunk)
                    for chunk in chunks
                ],
                total=uow.child_chunks.count_search(query),
                limit=query.limit,
                offset=query.offset,
            )
