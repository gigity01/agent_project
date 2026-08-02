"""获取单份文档完整状态的查询用例。"""

from collections.abc import Callable
from typing import Any

from app.modules.document.application.dto import DocumentResult
from app.modules.document.application.errors import DocumentApplicationError


class GetDocumentUseCase:
    """通过应用层查询文档，避免适配层直接访问 Repository。"""

    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: int) -> DocumentResult:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id)
            if document is None:
                raise DocumentApplicationError(404, "文档不存在")
            return DocumentResult.model_validate(document)
