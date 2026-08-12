"""处理文档应用用例：以短事务编排领取、执行与结果登记。"""

import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from app.modules.document.application.dto import (
    DocumentArtifactCreate,
    ProcessDocumentResult,
)
from app.modules.document.application.errors import DocumentApplicationError
from app.modules.document.application.failure_state import (
    FailureStateResult,
    NO_FAILURE_STATE_CHANGE,
)
from app.modules.document.application.ports import DocumentApplicationPorts
from app.modules.document.application.settings import (
    DocumentProcessingSettings,
)
from app.modules.document.application.use_cases.prepare_document_source import (
    PendingArtifact,
    PreparedProcessSource,
    prepare_process_source,
)
from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStatus,
    DocumentStorageStatus,
)
from app.shared.observability.document_process_logger import (
    DocumentProcessLogger,
)
from app.shared.observability.correlation import DocumentOperationContext


PROCESSABLE_LIFECYCLE_STATUSES = frozenset(
    {
        DocumentLifecycleStatus.ACTIVE.value,
        DocumentLifecycleStatus.SCHEDULED.value,
    }
)


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
    operation_id: str


@dataclass(frozen=True)
class ProcessingExecutionResult:
    """事务外处理完成、等待在完成事务中登记的结果。"""

    document_id: int
    operation_id: str
    cleaned_path: Path
    prepared_source: PreparedProcessSource
    cleaned_artifact: PendingArtifact

    @property
    def secondary_artifact(self) -> PendingArtifact | None:
        return self.prepared_source.secondary_artifact

class ProcessDocumentUseCase:
    """在短事务之间编排 Document 转换与清洗。"""

    def __init__(
        self,
        *,
        ports: DocumentApplicationPorts,
        settings: DocumentProcessingSettings,
    ) -> None:
        self._ports = ports
        self._settings = settings

    def execute(
        self,
        document_id: int,
        *,
        operation_context: DocumentOperationContext | None = None,
    ) -> ProcessDocumentResult:
        return _process_document(
            document_id,
            ports=self._ports,
            settings=self._settings,
            operation_context=operation_context,
        )


def _process_document(
    document_id: int,
    *,
    ports: DocumentApplicationPorts,
    settings: DocumentProcessingSettings,
    operation_context: DocumentOperationContext | None = None,
) -> ProcessDocumentResult:
    """领取文档后在事务外处理，并以独立短事务登记结果或失败。"""
    logger_kwargs = {"document_id": document_id}
    if operation_context is not None:
        logger_kwargs["operation_context"] = operation_context
    process_logger = DocumentProcessLogger(**logger_kwargs)
    operation_id = process_logger.operation_context.operation_id
    context: ProcessingContext | None = None
    phase = "claim"
    try:
        context = _claim_processing(
            document_id,
            operation_id=operation_id,
            ports=ports,
        )
        process_logger.claimed(context)

        with ports.external_effect_fence.hold(
            _process_effect_fence_key(document_id)
        ):
            _assert_processing_owned(context, ports=ports)
            phase = "execute"
            execution_result = _execute_processing(
                context,
                ports=ports,
                settings=settings,
            )

            phase = "promote"
            execution_result = _promote_processing_artifacts(
                execution_result,
                settings=settings,
            )

        phase = "finalize"
        response = _complete_processing(execution_result, ports=ports)
        process_logger.completed(
            processed_source_type=(
                execution_result.cleaned_artifact.artifact_format
            ),
            cleaned_uri=response.cleaned_uri,
        )
        return response
    except ProcessingAbortedError as exc:
        process_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=False,
            status_before=None,
            status_after=None,
        )
        raise DocumentApplicationError(
            status_code=409,
            detail=str(exc),
        ) from exc
    except DocumentApplicationError as exc:
        process_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=False,
            status_before=None,
            status_after=None,
        )
        raise
    except Exception as exc:
        process_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=False,
            status_before=None,
            status_after=None,
        )
        raise DocumentApplicationError(
            status_code=500,
            detail="文档处理失败，请稍后重试或联系管理员",
        ) from exc


def _claim_processing(
    document_id: int,
    *,
    operation_id: str,
    ports: DocumentApplicationPorts,
) -> ProcessingContext:
    """以行锁领取处理权，并立即提交 processing 状态。"""
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(document_id)

        if document is None:
            raise DocumentApplicationError(status_code=404, detail="文档不存在")
        if document.active_operation_id is not None:
            raise DocumentApplicationError(
                status_code=409,
                detail="文档已有未释放的处理 Operation",
            )
        if document.status not in {
            DocumentStatus.UPLOADED.value,
            DocumentStatus.FAILED.value,
        }:
            raise DocumentApplicationError(
                status_code=409,
                detail=f"当前文档状态不允许处理: {document.status}",
            )
        if document.lifecycle_status not in PROCESSABLE_LIFECYCLE_STATUSES:
            raise DocumentApplicationError(
                status_code=409,
                detail="失效文档不能处理",
            )
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise DocumentApplicationError(
                status_code=409,
                detail="文档不在活跃存储区",
            )

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
            operation_id=operation_id,
        )
        document.status = DocumentStatus.PROCESSING.value
        document.active_operation_id = operation_id
        uow.flush()
        uow.commit()

    return context


def _execute_processing(
    context: ProcessingContext,
    *,
    ports: DocumentApplicationPorts,
    settings: DocumentProcessingSettings,
) -> ProcessingExecutionResult:
    """在数据库事务外执行源检查、转换、清洗和文件元数据计算。"""
    if not context.source_path.exists():
        raise DocumentApplicationError(
            status_code=404,
            detail=f"原始文件不存在: {context.source_path}",
        )
    if not context.source_path.is_file():
        raise DocumentApplicationError(
            status_code=400,
            detail=f"原始路径不是有效文件: {context.source_path}",
        )

    operation_dir = _processing_operation_dir(
        settings,
        context.operation_id,
    )
    prepared_source = prepare_process_source(
        context,
        ports=ports,
        settings=settings,
        output_dir=operation_dir,
    )
    operation_dir.mkdir(parents=True, exist_ok=True)
    cleaned_filename = (
        f"{context.doc_code}.cleaned.{prepared_source.source_type}"
    )
    cleaned_path = operation_dir / cleaned_filename
    processor = ports.processor_factory(prepared_source.source_type)
    process_result = processor.process(
        source_path=prepared_source.source_path,
        cleaned_path=cleaned_path,
    )

    cleaned_artifact = PendingArtifact(
        artifact_type="cleaned_text",
        artifact_role="process_output",
        artifact_format=process_result.source_type,
        artifact_uri=str(cleaned_path),
        artifact_hash=ports.calculate_file_hash(cleaned_path),
        provider=None,
        processor=processor.__class__.__name__,
        file_size=cleaned_path.stat().st_size,
        char_count=process_result.char_count,
        line_count=process_result.line_count,
        metadata=process_result.metadata,
    )
    return ProcessingExecutionResult(
        document_id=context.document_id,
        operation_id=context.operation_id,
        cleaned_path=cleaned_path,
        prepared_source=prepared_source,
        cleaned_artifact=cleaned_artifact,
    )


def _assert_processing_owned(
    context: ProcessingContext,
    *,
    ports: DocumentApplicationPorts,
) -> None:
    """在文件副作用围栏内复核当前 Operation 仍持有处理权。"""
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(context.document_id)
        if (
            document is None
            or document.status != DocumentStatus.PROCESSING.value
            or document.active_operation_id != context.operation_id
        ):
            raise ProcessingAbortedError("当前处理 Operation ownership 已失效")
        if document.lifecycle_status not in PROCESSABLE_LIFECYCLE_STATUSES:
            raise ProcessingAbortedError("文档处理期间已经失效")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise ProcessingAbortedError("文档已进入归档流程")


def _complete_processing(
    result: ProcessingExecutionResult,
    *,
    ports: DocumentApplicationPorts,
) -> ProcessDocumentResult:
    """在短事务中复核状态、登记 Artifact 并推进到 processed。"""
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(result.document_id)

        if document is None:
            raise DocumentApplicationError(status_code=404, detail="文档不存在")
        if document.status != DocumentStatus.PROCESSING.value:
            raise ProcessingAbortedError(
                f"文档处理状态已经变化: {document.status}"
            )
        if document.active_operation_id != result.operation_id:
            raise ProcessingAbortedError("当前处理 Operation 已被其他执行接管")
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
        document.active_operation_id = None
        uow.flush()
        response = ProcessDocumentResult(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            source_uri=document.source_uri,
            cleaned_uri=document.cleaned_uri,
            status=document.status,
        )
        uow.commit()

    return response


def _promote_processing_artifacts(
    result: ProcessingExecutionResult,
    *,
    settings: DocumentProcessingSettings,
) -> ProcessingExecutionResult:
    """把 operation staging 产物提升到正式的 operation-scoped 目录。"""
    cleaned_dir = _operation_scoped_dir(
        settings.cleaned_storage_dir,
        result.operation_id,
    )
    cleaned_path = _promote_file(result.cleaned_path, cleaned_dir)
    cleaned_artifact = replace(
        result.cleaned_artifact,
        artifact_uri=str(cleaned_path),
    )

    prepared_source = result.prepared_source
    if result.secondary_artifact is not None:
        secondary_dir = _operation_scoped_dir(
            settings.secondary_text_storage_dir,
            result.operation_id,
        )
        secondary_path = _promote_file(
            prepared_source.source_path,
            secondary_dir,
        )
        prepared_source = replace(
            prepared_source,
            source_path=secondary_path,
            secondary_artifact=replace(
                result.secondary_artifact,
                artifact_uri=str(secondary_path),
            ),
        )

    operation_dir = _processing_operation_dir(settings, result.operation_id)
    if operation_dir.exists():
        shutil.rmtree(operation_dir)

    return replace(
        result,
        cleaned_path=cleaned_path,
        prepared_source=prepared_source,
        cleaned_artifact=cleaned_artifact,
    )


def _promote_file(source_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / source_path.name
    if destination_path.exists():
        raise RuntimeError(f"正式产物路径已存在: {destination_path}")
    shutil.move(str(source_path), str(destination_path))
    return destination_path


def _fail_processing(
    document_id: int,
    error: Exception,
    *,
    operation_id: str,
    ports: DocumentApplicationPorts,
) -> FailureStateResult:
    """围栏仍由指定 Operation 持有的 processing 文档。"""
    del error
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(document_id)
        if document is None:
            return NO_FAILURE_STATE_CHANGE
        status_before = document.status
        if document.active_operation_id != operation_id:
            return FailureStateResult(
                state_updated=False,
                status_before=status_before,
                status_after=document.status,
            )
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


class ProcessDocumentCompensator:
    """按 operation-scoped 目录补偿文档处理副作用。"""

    def __init__(
        self,
        *,
        ports: DocumentApplicationPorts,
        settings: DocumentProcessingSettings,
    ) -> None:
        self._ports = ports
        self._settings = settings

    def compensate(
        self,
        *,
        document_id: int,
        operation_id: str,
    ) -> FailureStateResult:
        failure_result = _fail_processing(
            document_id,
            RuntimeError("文档处理 Operation 需要补偿"),
            operation_id=operation_id,
            ports=self._ports,
        )
        with self._ports.external_effect_fence.hold(
            _process_effect_fence_key(document_id)
        ):
            with self._ports.uow_factory() as uow:
                document = uow.documents.get_by_id_for_update(document_id)
                owns_operation = (
                    document is not None
                    and document.active_operation_id == operation_id
                    and document.status == DocumentStatus.FAILED.value
                )
            if not owns_operation:
                return failure_result

            operation_dirs = tuple(
                dict.fromkeys(
                    (
                        _processing_operation_dir(
                            self._settings,
                            operation_id,
                        ),
                        _operation_scoped_dir(
                            self._settings.cleaned_storage_dir,
                            operation_id,
                        ),
                        _operation_scoped_dir(
                            self._settings.secondary_text_storage_dir,
                            operation_id,
                        ),
                    )
                )
            )
            for operation_dir in operation_dirs:
                if operation_dir.exists():
                    shutil.rmtree(operation_dir)

            with self._ports.uow_factory() as uow:
                document = uow.documents.get_by_id_for_update(document_id)
                if (
                    document is None
                    or document.active_operation_id != operation_id
                ):
                    return failure_result
                document.active_operation_id = None
                uow.flush()
                uow.commit()
        return failure_result


def _processing_operation_dir(
    settings: DocumentProcessingSettings,
    operation_id: str,
) -> Path:
    """返回不能逃逸 staging 根目录的 Operation 产物目录。"""
    return _operation_scoped_dir(settings.staging_storage_dir, operation_id)


def _process_effect_fence_key(document_id: int) -> str:
    return f"document:process:{document_id}"


def _operation_scoped_dir(root: Path, operation_id: str) -> Path:
    """返回不能逃逸指定根目录的 Operation 目录。"""
    if (
        not operation_id
        or Path(operation_id).name != operation_id
        or operation_id in {".", ".."}
    ):
        raise ValueError("operation_id 不能用于文件路径")
    return root / operation_id


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
