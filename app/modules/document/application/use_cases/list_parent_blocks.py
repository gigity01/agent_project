"""父级语义块条件查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import (
    ListParentBlocksResult,
    ParentBlockResult,
    ParentBlockSearchQuery,
)


class ListParentBlocksUseCase:
    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, query: ParentBlockSearchQuery) -> ListParentBlocksResult:
        with self._uow_factory() as uow:
            blocks = uow.parent_blocks.search(query)
            return ListParentBlocksResult(
                items=[
                    ParentBlockResult.model_validate(block)
                    for block in blocks
                ],
                total=uow.parent_blocks.count_search(query),
                limit=query.limit,
                offset=query.offset,
            )
