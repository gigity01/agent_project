"""文档切块领取、事务外执行和结果登记的短事务测试。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStatus,
    DocumentStorageStatus,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    ROOT_DIR
    / "app"
    / "modules"
    / "document"
    / "application"
    / "use_cases"
    / "build_chunks.py"
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
class _ChunkBuildInput:
    cleaned_path: Path
    document_title: str
    business_scene: str | None
    process_metadata: dict = field(default_factory=dict)


@dataclass
class _ParentBlockData:
    block_type: str
    title: str | None
    section_path: list[str] | None
    content: str
    block_index: int
    semantic_group_index: int
    segment_index: int


@dataclass
class _ChildChunkData:
    content: str
    embedding_text: str
    chunk_index: int
    section_path: list[str] | None = None
    source_row_index: int | None = None
    chunk_type: str = "text"


@dataclass
class _ChunkBuildResult:
    parents: list[_ParentBlockData]
    children_by_parent_index: dict[int, list[_ChildChunkData]]


class _DocumentChunkLogger:
    instances = []

    def __init__(self, *, document_id=None) -> None:
        self.document_id = document_id
        self.failed_fields = None
        self.__class__.instances.append(self)

    def claimed(self, context) -> None:
        self.context = context

    def build_started(self, context, *, chunker) -> None:
        self.chunker = chunker

    def build_completed(self, result, *, chunker) -> None:
        self.result = result

    def completed(self, response) -> None:
        self.response = response

    def failed(self, **fields) -> None:
        self.failed_fields = fields


def _load_service_module():
    replacements = {
        "app.modules.document.application.dto": types.ModuleType(
            "app.modules.document.application.dto"
        ),
        "app.modules.document.application.errors": types.ModuleType(
            "app.modules.document.application.errors"
        ),
        "app.modules.document.application.ports": types.ModuleType(
            "app.modules.document.application.ports"
        ),
        "app.modules.document.domain.models": types.ModuleType(
            "app.modules.document.domain.models"
        ),
        "app.modules.document.domain.policies": types.ModuleType(
            "app.modules.document.domain.policies"
        ),
        "app.shared.observability.document_chunk_logger": types.ModuleType(
            "app.shared.observability.document_chunk_logger"
        ),
    }

    replacements[
        "app.modules.document.application.dto"
    ].BuildChunksResult = _KeywordModel
    replacements[
        "app.modules.document.application.errors"
    ].DocumentApplicationError = _HTTPException
    ports = replacements["app.modules.document.application.ports"]
    ports.create_child_chunk = _KeywordModel
    ports.create_parent_block = _KeywordModel
    ports.create_uow = object
    ports.get_chunker = lambda source_type: None
    domain_models = replacements["app.modules.document.domain.models"]
    domain_models.ChunkBuildInput = _ChunkBuildInput
    domain_models.ChunkBuildResult = _ChunkBuildResult
    domain_models.ParentBlockData = _ParentBlockData
    domain_models.ChildChunkData = _ChildChunkData
    policies = replacements["app.modules.document.domain.policies"]
    policies.get_expected_process_output_type = lambda source_type: source_type
    policies.md5_text = lambda text: f"md5:{text}"
    setattr(
        replacements["app.shared.observability.document_chunk_logger"],
        "DocumentChunkLogger",
        _DocumentChunkLogger,
    )

    originals = {
        name: sys.modules.get(name)
        for name in replacements
    }

    sys.modules.update(replacements)

    try:
        spec = importlib.util.spec_from_file_location(
            "document_chunking_service_under_test",
            SERVICE_PATH,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的文档切块 Service")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        return module

    finally:
        sys.modules.pop(
            "document_chunking_service_under_test",
            None,
        )

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
    def __init__(self, artifact) -> None:
        self.artifact = artifact
        self.calls: list[dict] = []

    def get_latest_active(self, **criteria):
        self.calls.append(criteria)
        return self.artifact


class _ParentBlockRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.created: list[SimpleNamespace] = []

    def delete_by_doc_id(self, document_id: int) -> None:
        self.events.append(f"delete_parent:{document_id}")

    def create_many(self, parents):
        self.events.append("create_parents")
        for index, parent in enumerate(parents, start=101):
            parent.id = index
        self.created.extend(parents)
        return parents


class _ChildChunkRepository:
    def __init__(self, events: list[str], existing_chunks: bool) -> None:
        self.events = events
        self.existing_chunks = existing_chunks
        self.exists_calls: list[int] = []
        self.created: list[SimpleNamespace] = []

    def delete_by_doc_id(self, document_id: int) -> None:
        self.events.append(f"delete_child:{document_id}")

    def create_many(self, children):
        self.events.append("create_children")
        self.created.extend(children)
        return children

    def exists_by_doc_id(self, document_id: int) -> bool:
        self.exists_calls.append(document_id)
        return self.existing_chunks


class _UnitOfWork:
    def __init__(
        self,
        documents: dict[int, SimpleNamespace],
        artifact,
        existing_chunks: bool,
    ) -> None:
        self.events: list[str] = []
        self.documents = _DocumentRepository(documents)
        self.document_artifacts = _ArtifactRepository(artifact)
        self.parent_blocks = _ParentBlockRepository(self.events)
        self.child_chunks = _ChildChunkRepository(
            self.events,
            existing_chunks,
        )
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
    def __init__(
        self,
        documents: dict[int, SimpleNamespace],
        artifact,
        existing_chunks: bool,
    ) -> None:
        self.documents = documents
        self.artifact = artifact
        self.existing_chunks = existing_chunks
        self.instances: list[_UnitOfWork] = []

    def __call__(self) -> _UnitOfWork:
        uow = _UnitOfWork(
            self.documents,
            self.artifact,
            self.existing_chunks,
        )
        self.instances.append(uow)
        return uow


def _document(
    *,
    status: str = DocumentStatus.PROCESSED.value,
    lifecycle_status: str = DocumentLifecycleStatus.ACTIVE.value,
    storage_status: str = DocumentStorageStatus.ACTIVE.value,
    cleaned_uri: str | None = "cleaned.md",
    active_content_hash: str | None = "active-hash",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        doc_code="DOC_001",
        source_type="md",
        cleaned_uri=cleaned_uri,
        title="Document title",
        kb_id=10,
        domain_code="domain",
        business_scene="scene",
        version=1,
        status=status,
        lifecycle_status=lifecycle_status,
        storage_status=storage_status,
        active_content_hash=active_content_hash,
    )


def _artifact(path: str = "cleaned.md") -> SimpleNamespace:
    return SimpleNamespace(
        artifact_uri=path,
        artifact_format="md",
        metadata_json={"headings": 2},
    )


def _chunk_result() -> _ChunkBuildResult:
    parents = [
        _ParentBlockData(
            block_type="section",
            title="One",
            section_path=["One"],
            content="Parent one",
            block_index=0,
            semantic_group_index=0,
            segment_index=0,
        ),
        _ParentBlockData(
            block_type="section",
            title="Two",
            section_path=["Two"],
            content="Parent two",
            block_index=1,
            semantic_group_index=1,
            segment_index=0,
        ),
    ]
    children = {
        0: [
            _ChildChunkData(
                content="Child one",
                embedding_text="One\nChild one",
                chunk_index=0,
                section_path=["One"],
            )
        ],
        1: [
            _ChildChunkData(
                content="Child two",
                embedding_text="Two\nChild two",
                chunk_index=0,
                section_path=["Two"],
            )
        ],
    }
    return _ChunkBuildResult(parents, children)


class DocumentChunkingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = _load_service_module()

    def setUp(self) -> None:
        self.original_uow = getattr(self.service, "SQLAlchemyUnitOfWork")

    def tearDown(self) -> None:
        setattr(self.service, "SQLAlchemyUnitOfWork", self.original_uow)

    def _use_document(
        self,
        document: SimpleNamespace,
        artifact=None,
        *,
        existing_chunks: bool = False,
    ) -> _UnitOfWorkFactory:
        factory = _UnitOfWorkFactory(
            {document.id: document},
            artifact,
            existing_chunks,
        )
        setattr(self.service, "SQLAlchemyUnitOfWork", factory)
        return factory

    def test_processed_document_can_be_claimed(self) -> None:
        document = _document()
        factory = self._use_document(document, _artifact("artifact.md"))

        context = self.service._claim_chunking(document.id)

        self.assertEqual(document.status, DocumentStatus.CHUNKING.value)
        self.assertEqual(context.cleaned_path, Path("artifact.md"))
        self.assertEqual(context.process_metadata, {"headings": 2})
        self.assertEqual(factory.instances[0].documents.locked_ids, [document.id])
        self.assertEqual(factory.instances[0].commit_count, 1)

    def test_claim_failure_is_logged_without_failure_state_compensation(self) -> None:
        factory = _UnitOfWorkFactory({}, None, False)
        setattr(self.service, "SQLAlchemyUnitOfWork", factory)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.build_document_chunks(999)

        chunk_logger = self.service.DocumentChunkLogger.instances[-1]
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(chunk_logger.failed_fields["phase"], "claim")
        self.assertIsNone(chunk_logger.failed_fields["context"])
        self.assertEqual(len(factory.instances), 1)

    def test_failed_document_can_retry_with_cleaned_uri(self) -> None:
        document = _document(
            status=DocumentStatus.FAILED.value,
            cleaned_uri="legacy.md",
        )
        factory = self._use_document(document)

        context = self.service._claim_chunking(document.id)

        self.assertEqual(document.status, DocumentStatus.CHUNKING.value)
        self.assertEqual(context.cleaned_path, Path("legacy.md"))
        self.assertEqual(factory.instances[0].child_chunks.exists_calls, [1])
        self.assertEqual(factory.instances[0].commit_count, 1)

    def test_failed_document_with_existing_chunks_cannot_retry(self) -> None:
        document = _document(status=DocumentStatus.FAILED.value)
        factory = self._use_document(
            document,
            _artifact(),
            existing_chunks=True,
        )

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service._claim_chunking(document.id)

        claim_uow = factory.instances[0]
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            raised.exception.detail,
            "文档已有切块结果，不能通过切块接口重试",
        )
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(claim_uow.child_chunks.exists_calls, [document.id])
        self.assertEqual(claim_uow.document_artifacts.calls, [])
        self.assertEqual(claim_uow.commit_count, 0)

    def test_scheduled_document_can_be_claimed(self) -> None:
        document = _document(
            lifecycle_status=DocumentLifecycleStatus.SCHEDULED.value,
        )
        factory = self._use_document(document, _artifact())

        self.service._claim_chunking(document.id)

        self.assertEqual(document.status, DocumentStatus.CHUNKING.value)
        self.assertEqual(factory.instances[0].commit_count, 1)

    def test_missing_cleaned_source_is_rejected_before_claim(self) -> None:
        document = _document(
            status=DocumentStatus.FAILED.value,
            cleaned_uri=None,
        )
        factory = self._use_document(document)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service._claim_chunking(document.id)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(factory.instances[0].commit_count, 0)

    def test_chunking_document_cannot_be_claimed_again(self) -> None:
        document = _document(status=DocumentStatus.CHUNKING.value)
        factory = self._use_document(document, _artifact())

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service._claim_chunking(document.id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(factory.instances[0].commit_count, 0)

    def test_inactive_or_archiving_document_cannot_be_claimed(self) -> None:
        scenarios = [
            (DocumentLifecycleStatus.DELETED.value, "active"),
            (DocumentLifecycleStatus.EXPIRED.value, "active"),
            (DocumentLifecycleStatus.REPLACED.value, "active"),
            (DocumentLifecycleStatus.ACTIVE.value, "archiving"),
        ]
        for lifecycle_status, storage_status in scenarios:
            with self.subTest(
                lifecycle_status=lifecycle_status,
                storage_status=storage_status,
            ):
                document = _document(
                    lifecycle_status=lifecycle_status,
                    storage_status=storage_status,
                )
                factory = self._use_document(document, _artifact())

                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service._claim_chunking(document.id)

                self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(document.status, DocumentStatus.PROCESSED.value)
                self.assertEqual(factory.instances[0].commit_count, 0)

    def test_failure_state_result_preserves_concurrent_document_status(self) -> None:
        document = _document(status=DocumentStatus.INDEXED.value)
        factory = self._use_document(document, _artifact())

        result = self.service._fail_chunking(
            document.id,
            RuntimeError("failed"),
        )

        self.assertFalse(result.state_updated)
        self.assertEqual(result.status_before, DocumentStatus.INDEXED.value)
        self.assertEqual(result.status_after, DocumentStatus.INDEXED.value)
        self.assertEqual(document.status, DocumentStatus.INDEXED.value)
        self.assertEqual(factory.instances[0].commit_count, 0)

    def test_chunker_failure_marks_failed_without_releasing_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cleaned_path = Path(temp_dir) / "cleaned.md"
            cleaned_path.write_text("content", encoding="utf-8")
            document = _document(active_content_hash="keep-me")
            factory = self._use_document(document, _artifact(str(cleaned_path)))

            class FailingChunker:
                @staticmethod
                def build(input_data):
                    self.assertFalse(
                        any(uow.active for uow in factory.instances)
                    )
                    raise RuntimeError("chunker failed")

            with mock.patch.object(
                self.service,
                "get_chunker",
                return_value=FailingChunker(),
            ):
                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service.build_document_chunks(document.id)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(document.active_content_hash, "keep-me")
        self.assertEqual(len(factory.instances), 2)
        self.assertEqual(factory.instances[0].commit_count, 1)
        self.assertEqual(factory.instances[1].commit_count, 1)

    def test_invalid_chunk_build_results_are_rejected(self) -> None:
        duplicate_parent = _chunk_result()
        duplicate_parent.parents.append(
            _ParentBlockData(
                block_type="section",
                title="Duplicate",
                section_path=["Duplicate"],
                content="Duplicate parent",
                block_index=0,
                semantic_group_index=2,
                segment_index=0,
            )
        )

        no_children = _chunk_result()
        no_children.children_by_parent_index = {}

        unknown_parent = _chunk_result()
        unknown_parent.children_by_parent_index[99] = [
            _ChildChunkData(
                content="Unknown",
                embedding_text="Unknown child",
                chunk_index=0,
            )
        ]

        duplicate_child = _chunk_result()
        duplicate_child.children_by_parent_index[0].append(
            _ChildChunkData(
                content="Duplicate child",
                embedding_text="Duplicate child",
                chunk_index=0,
            )
        )

        empty_embedding = _chunk_result()
        empty_embedding.children_by_parent_index[0][0].embedding_text = "   "

        scenarios = [
            (
                duplicate_parent,
                500,
                "切块结果包含重复的 parent block_index",
            ),
            (no_children, 400, "未生成任何 child chunk"),
            (
                unknown_parent,
                500,
                "切块结果引用了不存在的 parent block",
            ),
            (duplicate_child, 500, "切块结果包含重复的 chunk_index"),
            (empty_embedding, 500, "切块结果包含空的 embedding_text"),
        ]
        for chunks, status_code, detail in scenarios:
            with self.subTest(detail=detail):
                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service._validate_chunk_build_result(chunks)

                self.assertEqual(raised.exception.status_code, status_code)
                self.assertEqual(raised.exception.detail, detail)

    def test_completion_replaces_and_batches_blocks_in_one_uow(self) -> None:
        document = _document(status=DocumentStatus.CHUNKING.value)
        factory = self._use_document(document, _artifact())
        context = self.service.ChunkingContext(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            cleaned_path=Path("cleaned.md"),
            chunk_source_type="md",
            document_title=document.title,
            kb_id=document.kb_id,
            domain_code=document.domain_code,
            business_scene=document.business_scene,
            version=document.version,
            process_metadata={},
            status_before=DocumentStatus.PROCESSED.value,
        )
        result = self.service.ChunkingExecutionResult(
            context=context,
            chunks=_chunk_result(),
        )

        response = self.service._complete_chunking(result)

        complete_uow = factory.instances[0]
        self.assertEqual(
            complete_uow.events,
            [
                "delete_child:1",
                "delete_parent:1",
                "create_parents",
                "create_children",
            ],
        )
        self.assertEqual(document.status, DocumentStatus.CHUNKED.value)
        self.assertEqual(response.parent_count, 2)
        self.assertEqual(response.child_count, 2)
        self.assertEqual(complete_uow.commit_count, 1)
        self.assertEqual(
            [child.parent_id for child in complete_uow.child_chunks.created],
            [101, 102],
        )
        self.assertTrue(
            all(
                child.vector_status == "pending"
                for child in complete_uow.child_chunks.created
            )
        )

    def test_deletion_during_execution_discards_chunks_and_marks_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cleaned_path = Path(temp_dir) / "cleaned.md"
            cleaned_path.write_text("content", encoding="utf-8")
            document = _document()
            factory = self._use_document(document, _artifact(str(cleaned_path)))

            class DeletingChunker:
                @staticmethod
                def build(input_data):
                    document.lifecycle_status = DocumentLifecycleStatus.DELETED.value
                    document.storage_status = DocumentStorageStatus.ARCHIVING.value
                    document.active_content_hash = None
                    return _chunk_result()

            with mock.patch.object(
                self.service,
                "get_chunker",
                return_value=DeletingChunker(),
            ):
                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service.build_document_chunks(document.id)

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
        self.assertEqual(completion_uow.events, [])
        self.assertEqual(completion_uow.commit_count, 0)
        self.assertEqual(factory.instances[2].commit_count, 1)


if __name__ == "__main__":
    unittest.main()
