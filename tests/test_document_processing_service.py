"""文档处理领取、事务外执行和结果登记的短事务测试。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_status import DocumentStatus
from app.constants.document_storage_status import DocumentStorageStatus


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    ROOT_DIR
    / "app"
    / "modules"
    / "document"
    / "application"
    / "use_cases"
    / "process_document.py"
)


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _KeywordModel(SimpleNamespace):
    def __init__(self, **values) -> None:
        super().__init__(**values)


@dataclass(frozen=True)
class _PendingArtifact:
    artifact_type: str
    artifact_role: str
    artifact_format: str
    artifact_uri: str
    artifact_hash: str
    provider: str | None
    processor: str | None
    file_size: int
    char_count: int
    line_count: int
    metadata: dict | None


@dataclass(frozen=True)
class _PreparedProcessSource:
    source_path: Path
    source_type: str
    generated_secondary_text: bool = False
    secondary_artifact: _PendingArtifact | None = None

    def cleanup_generated_file(self) -> None:
        if self.generated_secondary_text:
            self.source_path.unlink(missing_ok=True)


class _DocumentProcessLogger:
    instances = []

    def __init__(self, *, document_id=None) -> None:
        self.document_id = document_id
        self.claimed_fields = None
        self.completed_fields = None
        self.failed_fields = None
        self.__class__.instances.append(self)

    def claimed(self, context) -> None:
        self.claimed_fields = {"context": context}

    def completed(self, **fields) -> None:
        self.completed_fields = fields

    def failed(self, **fields) -> None:
        self.failed_fields = fields


def _load_service_module():
    replacements = {
        "fastapi": types.ModuleType("fastapi"),
        "app.app_config.settings": types.ModuleType("app.app_config.settings"),
        "app.app_utils.file_security": types.ModuleType(
            "app.app_utils.file_security"
        ),
        "app.db.uow": types.ModuleType("app.db.uow"),
        "app.processors.factory": types.ModuleType("app.processors.factory"),
        "app.schemas.document": types.ModuleType("app.schemas.document"),
        "app.schemas.document_artifact": types.ModuleType(
            "app.schemas.document_artifact"
        ),
        "app.services.document_source_prepare_service": types.ModuleType(
            "app.services.document_source_prepare_service"
        ),
        "core.observability.document_process_logger": types.ModuleType(
            "core.observability.document_process_logger"
        ),
    }
    replacements["fastapi"].HTTPException = _HTTPException
    replacements["app.app_config.settings"].CLEANED_STORAGE_DIR = Path("cleaned")
    replacements["app.app_utils.file_security"].calculate_file_hash = (
        lambda path: "hash"
    )
    replacements["app.db.uow"].SQLAlchemyUnitOfWork = object
    replacements["app.processors.factory"].get_processor = lambda source_type: None
    replacements["app.schemas.document"].DocumentProcessResponse = _KeywordModel
    replacements["app.schemas.document_artifact"].DocumentArtifactCreate = (
        _KeywordModel
    )

    prepare_module = replacements["app.services.document_source_prepare_service"]
    prepare_module.PendingArtifact = _PendingArtifact
    prepare_module.PreparedProcessSource = _PreparedProcessSource
    prepare_module.prepare_process_source = lambda context: None
    replacements[
        "core.observability.document_process_logger"
    ].DocumentProcessLogger = _DocumentProcessLogger

    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "document_processing_service_under_test",
            SERVICE_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的文档处理 Service")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("document_processing_service_under_test", None)
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class _DocumentRepository:
    def __init__(self, documents: dict[int, SimpleNamespace]) -> None:
        self.documents = documents
        self.locked_ids: list[int] = []

    def get_by_id_for_update(self, document_id: int):
        self.locked_ids.append(document_id)
        return self.documents.get(document_id)


class _ArtifactRepository:
    def __init__(self) -> None:
        self.superseded_calls: list[dict] = []
        self.create_calls: list[SimpleNamespace] = []

    def mark_active_as_superseded(self, **criteria) -> int:
        self.superseded_calls.append(criteria)
        return 0

    def create(self, artifact):
        self.create_calls.append(artifact)
        return artifact


class _UnitOfWork:
    def __init__(self, documents: dict[int, SimpleNamespace]) -> None:
        self.documents = _DocumentRepository(documents)
        self.document_artifacts = _ArtifactRepository()
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.active = False

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is not None or self.commit_count == 0:
            self.rollback_count += 1
        self.active = False
        return False

    def flush(self) -> None:
        self.flush_count += 1

    def commit(self) -> None:
        self.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self, documents: dict[int, SimpleNamespace]) -> None:
        self.documents = documents
        self.instances: list[_UnitOfWork] = []

    def __call__(self) -> _UnitOfWork:
        uow = _UnitOfWork(self.documents)
        self.instances.append(uow)
        return uow


def _document(
    *,
    status: str = DocumentStatus.UPLOADED.value,
    lifecycle_status: str = DocumentLifecycleStatus.ACTIVE.value,
    storage_status: str = DocumentStorageStatus.ACTIVE.value,
    source_uri: str = "source.txt",
    active_content_hash: str | None = "active-hash",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        doc_code="DOC_001",
        kb_id=10,
        domain_code="domain",
        business_scene="scene",
        source_type="txt",
        source_uri=source_uri,
        cleaned_uri=None,
        created_by_actor_code="operator",
        status=status,
        lifecycle_status=lifecycle_status,
        storage_status=storage_status,
        active_content_hash=active_content_hash,
    )


def _pending_artifact(
    service,
    *,
    artifact_type: str,
    artifact_role: str,
    artifact_uri: str,
) -> _PendingArtifact:
    return service.PendingArtifact(
        artifact_type=artifact_type,
        artifact_role=artifact_role,
        artifact_format="md",
        artifact_uri=artifact_uri,
        artifact_hash="artifact-hash",
        provider="provider" if artifact_type == "secondary_text" else None,
        processor="Processor",
        file_size=10,
        char_count=8,
        line_count=2,
        metadata={"kind": artifact_type},
    )


class DocumentProcessingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = _load_service_module()

    def setUp(self) -> None:
        self.original_uow = self.service.SQLAlchemyUnitOfWork

    def tearDown(self) -> None:
        self.service.SQLAlchemyUnitOfWork = self.original_uow

    def _use_document(self, document: SimpleNamespace) -> _UnitOfWorkFactory:
        factory = _UnitOfWorkFactory({document.id: document})
        self.service.SQLAlchemyUnitOfWork = factory
        return factory

    def test_uploaded_document_can_be_claimed(self) -> None:
        document = _document()
        factory = self._use_document(document)

        context = self.service._claim_processing(document.id)

        self.assertEqual(context.document_id, document.id)
        self.assertEqual(document.status, DocumentStatus.PROCESSING.value)
        self.assertEqual(factory.instances[0].documents.locked_ids, [document.id])
        self.assertEqual(factory.instances[0].flush_count, 1)
        self.assertEqual(factory.instances[0].commit_count, 1)

    def test_claim_failure_is_logged_without_failure_state_compensation(self) -> None:
        factory = _UnitOfWorkFactory({})
        self.service.SQLAlchemyUnitOfWork = factory

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.process_document(999)

        process_logger = self.service.DocumentProcessLogger.instances[-1]
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(process_logger.document_id, 999)
        self.assertEqual(process_logger.failed_fields["phase"], "claim")
        self.assertIsNone(process_logger.failed_fields["context"])
        self.assertEqual(len(factory.instances), 1)

    def test_failed_document_can_be_claimed_for_retry(self) -> None:
        document = _document(status=DocumentStatus.FAILED.value)
        factory = self._use_document(document)

        self.service._claim_processing(document.id)

        self.assertEqual(document.status, DocumentStatus.PROCESSING.value)
        self.assertEqual(factory.instances[0].commit_count, 1)

    def test_scheduled_document_in_active_storage_can_be_claimed(self) -> None:
        document = _document(
            lifecycle_status=DocumentLifecycleStatus.SCHEDULED.value,
        )
        factory = self._use_document(document)

        self.service._claim_processing(document.id)

        self.assertEqual(document.status, DocumentStatus.PROCESSING.value)
        self.assertEqual(factory.instances[0].commit_count, 1)

    def test_processing_document_cannot_be_claimed_again(self) -> None:
        document = _document(status=DocumentStatus.PROCESSING.value)
        factory = self._use_document(document)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service._claim_processing(document.id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(document.status, DocumentStatus.PROCESSING.value)
        self.assertEqual(factory.instances[0].commit_count, 0)

    def test_inactive_documents_cannot_be_claimed(self) -> None:
        for lifecycle_status in (
            DocumentLifecycleStatus.DELETED.value,
            DocumentLifecycleStatus.EXPIRED.value,
            DocumentLifecycleStatus.REPLACED.value,
        ):
            with self.subTest(lifecycle_status=lifecycle_status):
                document = _document(lifecycle_status=lifecycle_status)
                factory = self._use_document(document)

                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service._claim_processing(document.id)

                self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(document.status, DocumentStatus.UPLOADED.value)
                self.assertEqual(factory.instances[0].commit_count, 0)

    def test_document_outside_active_storage_cannot_be_claimed(self) -> None:
        document = _document(
            storage_status=DocumentStorageStatus.ARCHIVING.value,
        )
        factory = self._use_document(document)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service._claim_processing(document.id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(document.status, DocumentStatus.UPLOADED.value)
        self.assertEqual(factory.instances[0].commit_count, 0)

    def test_failure_state_result_preserves_concurrent_document_status(self) -> None:
        document = _document(status=DocumentStatus.PROCESSED.value)
        factory = self._use_document(document)

        result = self.service._fail_processing(
            document.id,
            RuntimeError("failed"),
        )

        self.assertFalse(result.state_updated)
        self.assertEqual(result.status_before, DocumentStatus.PROCESSED.value)
        self.assertEqual(result.status_after, DocumentStatus.PROCESSED.value)
        self.assertEqual(document.status, DocumentStatus.PROCESSED.value)
        self.assertEqual(factory.instances[0].commit_count, 0)

    def test_docling_failure_marks_failed_without_releasing_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.pdf"
            source_path.write_bytes(b"pdf")
            document = _document(
                source_uri=str(source_path),
                active_content_hash="keep-me",
            )
            factory = self._use_document(document)

            def fail_docling(context):
                self.assertFalse(any(uow.active for uow in factory.instances))
                raise RuntimeError("Docling failed")

            with mock.patch.object(
                self.service,
                "prepare_process_source",
                side_effect=fail_docling,
            ):
                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service.process_document(document.id)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(document.active_content_hash, "keep-me")
        self.assertEqual(len(factory.instances), 2)
        self.assertEqual(factory.instances[0].commit_count, 1)
        self.assertEqual(factory.instances[1].commit_count, 1)

    def test_completion_persists_artifacts_and_processed_in_one_uow(self) -> None:
        document = _document(status=DocumentStatus.PROCESSING.value)
        factory = self._use_document(document)
        secondary = _pending_artifact(
            self.service,
            artifact_type="secondary_text",
            artifact_role="process_input",
            artifact_uri="DOC_001_ART_DOCLING_MD_TOKEN.md",
        )
        cleaned = _pending_artifact(
            self.service,
            artifact_type="cleaned_text",
            artifact_role="process_output",
            artifact_uri="DOC_001.cleaned.md",
        )
        prepared = self.service.PreparedProcessSource(
            source_path=Path(secondary.artifact_uri),
            source_type="md",
            generated_secondary_text=True,
            secondary_artifact=secondary,
        )
        result = self.service.ProcessingExecutionResult(
            document_id=document.id,
            cleaned_path=Path(cleaned.artifact_uri),
            prepared_source=prepared,
            cleaned_artifact=cleaned,
        )

        response = self.service._complete_processing(result)

        complete_uow = factory.instances[0]
        self.assertEqual(document.status, DocumentStatus.PROCESSED.value)
        self.assertEqual(document.cleaned_uri, cleaned.artifact_uri)
        self.assertEqual(response.status, DocumentStatus.PROCESSED.value)
        self.assertEqual(len(complete_uow.document_artifacts.create_calls), 2)
        self.assertEqual(len(complete_uow.document_artifacts.superseded_calls), 2)
        self.assertEqual(complete_uow.commit_count, 1)

    def test_deletion_during_execution_discards_results_and_marks_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cleaned_path = temp_path / "cleaned.md"
            secondary_path = temp_path / "secondary.md"
            cleaned_path.write_text("cleaned", encoding="utf-8")
            secondary_path.write_text("secondary", encoding="utf-8")
            document = _document()
            factory = self._use_document(document)
            secondary = _pending_artifact(
                self.service,
                artifact_type="secondary_text",
                artifact_role="process_input",
                artifact_uri=str(secondary_path),
            )
            cleaned = _pending_artifact(
                self.service,
                artifact_type="cleaned_text",
                artifact_role="process_output",
                artifact_uri=str(cleaned_path),
            )
            result = self.service.ProcessingExecutionResult(
                document_id=document.id,
                cleaned_path=cleaned_path,
                prepared_source=self.service.PreparedProcessSource(
                    source_path=secondary_path,
                    source_type="md",
                    generated_secondary_text=True,
                    secondary_artifact=secondary,
                ),
                cleaned_artifact=cleaned,
            )

            def finish_after_deletion(context):
                document.lifecycle_status = DocumentLifecycleStatus.DELETED.value
                document.storage_status = DocumentStorageStatus.ARCHIVING.value
                document.active_content_hash = None
                return result

            with mock.patch.object(
                self.service,
                "_execute_processing",
                side_effect=finish_after_deletion,
            ):
                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service.process_document(document.id)

            self.assertFalse(cleaned_path.exists())
            self.assertFalse(secondary_path.exists())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(
            document.lifecycle_status,
            DocumentLifecycleStatus.DELETED.value,
        )
        self.assertEqual(
            document.storage_status,
            DocumentStorageStatus.ARCHIVING.value,
        )
        self.assertEqual(len(factory.instances), 3)
        completion_uow = factory.instances[1]
        self.assertEqual(completion_uow.document_artifacts.create_calls, [])
        self.assertEqual(completion_uow.commit_count, 0)
        self.assertEqual(factory.instances[2].commit_count, 1)


if __name__ == "__main__":
    unittest.main()
