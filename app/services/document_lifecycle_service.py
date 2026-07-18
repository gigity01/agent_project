"""文档业务失效事务编排。"""

from fastapi import HTTPException

from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_status import DocumentStatus
from app.db.uow import SQLAlchemyUnitOfWork
from app.models.document import Document
from app.schemas.document import DocumentResponse


DEACTIVATION_REASONS = frozenset(
    {
        DocumentLifecycleStatus.EXPIRED,
        DocumentLifecycleStatus.REPLACED,
        DocumentLifecycleStatus.DELETED,
    }
)
INACTIVE_LIFECYCLE_STATUSES = frozenset(
    status.value for status in DEACTIVATION_REASONS
)
ACTIVE_LIFECYCLE_STATUSES = frozenset(
    {
        DocumentLifecycleStatus.ACTIVE.value,
        DocumentLifecycleStatus.SCHEDULED.value,
    }
)


def _validate_replacement(
    document: Document,
    replacement: Document,
) -> None:
    """校验替代文档已在同一知识库完成索引并处于业务有效状态。"""
    if replacement.id == document.id:
        raise HTTPException(status_code=400, detail="文档不能替代自身")
    if replacement.kb_id != document.kb_id:
        raise HTTPException(
            status_code=409,
            detail="替代文档必须属于同一知识库",
        )
    if replacement.status != DocumentStatus.INDEXED.value:
        raise HTTPException(
            status_code=409,
            detail="替代文档尚未完成索引",
        )
    if replacement.lifecycle_status != DocumentLifecycleStatus.ACTIVE.value:
        raise HTTPException(
            status_code=409,
            detail="替代文档不是业务有效文档",
        )


def deactivate_document(
    document_id: int,
    reason: DocumentLifecycleStatus,
    *,
    replaced_by: int | None = None,
) -> DocumentResponse:
    """在单一事务中失效文档、释放内容 Hash，并标记为等待归档。"""
    if not isinstance(reason, DocumentLifecycleStatus) or reason not in DEACTIVATION_REASONS:
        raise ValueError("不支持的失效原因")

    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")

        if document.lifecycle_status == reason.value:
            return DocumentResponse.model_validate(document)

        if document.lifecycle_status in INACTIVE_LIFECYCLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"文档已经失效: {document.lifecycle_status}",
            )
        if document.lifecycle_status not in ACTIVE_LIFECYCLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"文档生命周期状态无效: {document.lifecycle_status}",
            )

        if reason == DocumentLifecycleStatus.REPLACED:
            if replaced_by is None:
                raise HTTPException(
                    status_code=400,
                    detail="替代操作必须指定新文档",
                )
            if replaced_by == document.id:
                raise HTTPException(status_code=400, detail="文档不能替代自身")

            replacement = uow.documents.get_by_id_for_update(replaced_by)
            if replacement is None:
                raise HTTPException(status_code=404, detail="替代文档不存在")
            _validate_replacement(document, replacement)

        updated_document = uow.documents.deactivate(
            document,
            lifecycle_status=reason.value,
            replaced_by=replaced_by,
        )
        response = DocumentResponse.model_validate(updated_document)
        uow.commit()

    return response
