"""处理文档应用用例：以短事务编排领取、执行与结果登记。"""

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.app_config.settings import CLEANED_STORAGE_DIR
from app.app_utils.file_security import calculate_file_hash
from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_status import DocumentStatus
from app.constants.document_storage_status import DocumentStorageStatus
from app.db.uow import SQLAlchemyUnitOfWork
from app.processors.factory import get_processor
from app.schemas.document import DocumentProcessResponse
from app.schemas.document_artifact import DocumentArtifactCreate
from app.services.document_failure_state import (
    FailureStateResult,
    NO_FAILURE_STATE_CHANGE,
)
from app.services.document_source_prepare_service import (
    PendingArtifact,
    PreparedProcessSource,
    prepare_process_source,
)
from core.observability.document_process_logger import DocumentProcessLogger


PROCESSABLE_LIFECYCLE_STATUSES = frozenset(
    {
        DocumentLifecycleStatus.ACTIVE.value,
        DocumentLifecycleStatus.SCHEDULED.value,
    }
)
logger = logging.getLogger(__name__)


class ProcessingAbortedError(RuntimeError):
    """表示任务执行期间文档状态变化，结果不得登记。"""


@dataclass(frozen=True)
class ProcessingContext:
    """领取事务提交后，执行阶段所需的不可变文档快照。"""

    document_id: int
    doc_code: str
    kb_id: int
    domain_code: str | None
    business_scene: str | None
    source_type: str
    source_path: Path
    created_by_actor_code: str | None
    status_before: str


@dataclass(frozen=True)
class ProcessingExecutionResult:
    """事务外处理完成、等待在完成事务中登记的结果。"""

    document_id: int
    cleaned_path: Path
    prepared_source: PreparedProcessSource
    cleaned_artifact: PendingArtifact

    @property
    def secondary_artifact(self) -> PendingArtifact | None:
        return self.prepared_source.secondary_artifact

    def cleanup_generated_files(self) -> None:
        """删除本次尚未成功登记的 cleaned 和 secondary 文件。"""
        try:
            self.cleaned_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.prepared_source.cleanup_generated_file()


def process_document(document_id: int) -> DocumentProcessResponse:
    """领取文档后在事务外处理，并以独立短事务登记结果或失败。"""
    process_logger = DocumentProcessLogger(document_id=document_id)
    context: ProcessingContext | None = None
    execution_result: ProcessingExecutionResult | None = None
    phase = "claim"
    try:
        context = _claim_processing(document_id)
        process_logger.claimed(context)

        phase = "execute"
        execution_result = _execute_processing(context)

        phase = "finalize"
        response = _complete_processing(execution_result)
        process_logger.completed(
            processed_source_type=(
                execution_result.cleaned_artifact.artifact_format
            ),
            cleaned_uri=response.cleaned_uri,
        )
        return response
    except ProcessingAbortedError as exc:
        failure_result = _register_processing_failure(
            document_id=document_id,
            error=exc,
            claimed=context is not None,
        )
        if execution_result is not None:
            execution_result.cleanup_generated_files()
        process_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=failure_result.state_updated,
            status_before=failure_result.status_before,
            status_after=failure_result.status_after,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException as exc:
        failure_result = _register_processing_failure(
            document_id=document_id,
            error=exc,
            claimed=context is not None,
        )
        if execution_result is not None:
            execution_result.cleanup_generated_files()
        process_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=failure_result.state_updated,
            status_before=failure_result.status_before,
            status_after=failure_result.status_after,
        )
        raise
    except Exception as exc:
        failure_result = _register_processing_failure(
            document_id=document_id,
            error=exc,
            claimed=context is not None,
        )
        if execution_result is not None:
            execution_result.cleanup_generated_files()
        process_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=failure_result.state_updated,
            status_before=failure_result.status_before,
            status_after=failure_result.status_after,
        )
        raise HTTPException(
            status_code=500,
            detail="文档处理失败，请稍后重试或联系管理员",
        ) from exc


def _claim_processing(document_id: int) -> ProcessingContext:
    """以行锁领取处理权，并立即提交 processing 状态。"""
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(document_id)

        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if document.status not in {
            DocumentStatus.UPLOADED.value,
            DocumentStatus.FAILED.value,
        }:
            raise HTTPException(
                status_code=409,
                detail=f"当前文档状态不允许处理: {document.status}",
            )
        if document.lifecycle_status not in PROCESSABLE_LIFECYCLE_STATUSES:
            raise HTTPException(status_code=409, detail="失效文档不能处理")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise HTTPException(status_code=409, detail="文档不在活跃存储区")

        status_before = document.status
        context = ProcessingContext(
            document_id=document.id,
            doc_code=document.doc_code,
            kb_id=document.kb_id,
            domain_code=document.domain_code,
            business_scene=document.business_scene,
            source_type=document.source_type,
            source_path=Path(document.source_uri),
            created_by_actor_code=document.created_by_actor_code,
            status_before=status_before,
        )
        document.status = DocumentStatus.PROCESSING.value
        uow.flush()
        uow.commit()

    return context


def _execute_processing(
    context: ProcessingContext,
) -> ProcessingExecutionResult:
    """在数据库事务外执行源检查、转换、清洗和文件元数据计算。"""
    if not context.source_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"原始文件不存在: {context.source_path}",
        )
    if not context.source_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"原始路径不是有效文件: {context.source_path}",
        )

    prepared_source: PreparedProcessSource | None = None
    cleaned_path: Path | None = None
    try:
        prepared_source = prepare_process_source(context)
        CLEANED_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        cleaned_filename = (
            f"{context.doc_code}.cleaned.{prepared_source.source_type}"
        )
        cleaned_path = CLEANED_STORAGE_DIR / cleaned_filename
        processor = get_processor(prepared_source.source_type)
        process_result = processor.process(
            source_path=prepared_source.source_path,
            cleaned_path=cleaned_path,
        )

        cleaned_artifact = PendingArtifact(
            artifact_type="cleaned_text",
            artifact_role="process_output",
            artifact_format=process_result.source_type,
            artifact_uri=str(cleaned_path),
            artifact_hash=calculate_file_hash(cleaned_path),
            provider=None,
            processor=processor.__class__.__name__,
            file_size=cleaned_path.stat().st_size,
            char_count=process_result.char_count,
            line_count=process_result.line_count,
            metadata=process_result.metadata,
        )
        return ProcessingExecutionResult(
            document_id=context.document_id,
            cleaned_path=cleaned_path,
            prepared_source=prepared_source,
            cleaned_artifact=cleaned_artifact,
        )
    except Exception:
        if cleaned_path is not None:
            try:
                cleaned_path.unlink(missing_ok=True)
            except OSError:
                pass
        if prepared_source is not None:
            prepared_source.cleanup_generated_file()
        raise


def _complete_processing(
    result: ProcessingExecutionResult,
) -> DocumentProcessResponse:
    """在短事务中复核状态、登记 Artifact 并推进到 processed。"""
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(result.document_id)

        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if document.status != DocumentStatus.PROCESSING.value:
            raise HTTPException(
                status_code=409,
                detail=f"文档处理状态已经变化: {document.status}",
            )
        if document.lifecycle_status not in PROCESSABLE_LIFECYCLE_STATUSES:
            raise ProcessingAbortedError("文档处理期间已经失效")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise ProcessingAbortedError("文档已进入归档流程")

        if result.secondary_artifact is not None:
            _persist_secondary_artifact(
                uow=uow,
                document=document,
                artifact=result.secondary_artifact,
            )
        _persist_cleaned_artifact(
            uow=uow,
            document=document,
            artifact=result.cleaned_artifact,
        )

        document.cleaned_uri = str(result.cleaned_path)
        document.status = DocumentStatus.PROCESSED.value
        uow.flush()
        response = DocumentProcessResponse(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            source_uri=document.source_uri,
            cleaned_uri=document.cleaned_uri,
            status=document.status,
        )
        uow.commit()

    return response


def _register_processing_failure(
    *,
    document_id: int,
    error: Exception,
    claimed: bool,
) -> FailureStateResult:
    """尽力登记失败状态；登记异常时保留原始业务异常。"""
    if not claimed:
        return NO_FAILURE_STATE_CHANGE
    try:
        return _fail_processing(document_id, error)
    except Exception:
        logger.exception(
            "文档处理失败状态登记失败",
            extra={"document_id": document_id},
        )
        return NO_FAILURE_STATE_CHANGE


def _fail_processing(
    document_id: int,
    error: Exception,
) -> FailureStateResult:
    """仅在任务仍为 processing 时，以独立短事务标记处理失败。"""
    del error
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(document_id)
        if document is None:
            return NO_FAILURE_STATE_CHANGE
        status_before = document.status
        if document.status == DocumentStatus.PROCESSING.value:
            document.status = DocumentStatus.FAILED.value
            uow.flush()
            uow.commit()
            return FailureStateResult(
                state_updated=True,
                status_before=status_before,
                status_after=document.status,
            )
        return FailureStateResult(
            state_updated=False,
            status_before=status_before,
            status_after=document.status,
        )


def _persist_secondary_artifact(*, uow, document, artifact: PendingArtifact) -> None:
    """登记本次 Docling 二级文本，并淘汰旧的 active 版本。"""
    artifact_code = Path(artifact.artifact_uri).stem
    _persist_artifact(
        uow=uow,
        document=document,
        artifact=artifact,
        artifact_code=artifact_code,
    )


def _persist_cleaned_artifact(*, uow, document, artifact: PendingArtifact) -> None:
    """登记本次 cleaned 文本，并淘汰旧的 active 版本。"""
    _persist_artifact(
        uow=uow,
        document=document,
        artifact=artifact,
        artifact_code=_generate_cleaned_artifact_code(
            document.doc_code,
            artifact.artifact_format,
        ),
    )


def _persist_artifact(
    *,
    uow,
    document,
    artifact: PendingArtifact,
    artifact_code: str,
) -> None:
    """在当前 UoW 中把待登记产物转换为持久化模型。"""
    uow.document_artifacts.mark_active_as_superseded(
        document_id=document.id,
        artifact_type=artifact.artifact_type,
        artifact_role=artifact.artifact_role,
        artifact_format=artifact.artifact_format,
    )
    uow.document_artifacts.create(
        DocumentArtifactCreate(
            document_id=document.id,
            artifact_code=artifact_code,
            artifact_type=artifact.artifact_type,
            artifact_role=artifact.artifact_role,
            artifact_format=artifact.artifact_format,
            artifact_uri=artifact.artifact_uri,
            artifact_hash=artifact.artifact_hash,
            provider=artifact.provider,
            processor=artifact.processor,
            file_size=artifact.file_size,
            char_count=artifact.char_count,
            line_count=artifact.line_count,
            status="active",
            metadata=artifact.metadata or {},
            created_by_actor_code=document.created_by_actor_code,
        )
    )


def _generate_cleaned_artifact_code(
    doc_code: str,
    artifact_format: str,
) -> str:
    """生成不超过 Artifact 字段长度的唯一 cleaned 产物编号。"""
    suffix = (
        f"_ART_CLEANED_{artifact_format.upper()}_"
        f"{uuid4().hex[:12].upper()}"
    )
    return f"{doc_code[:100 - len(suffix)]}{suffix}"
