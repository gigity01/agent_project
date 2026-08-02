"""Document Application 查询用例测试。"""

from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace

from app.modules.document.application.dto import DocumentListQuery
from app.modules.document.application.errors import DocumentApplicationError
from app.modules.document.application.use_cases.get_document import (
    GetDocumentUseCase,
)
from app.modules.document.application.use_cases.get_pipeline_state import (
    GetDocumentPipelineStateUseCase,
)
from app.modules.document.application.use_cases.list_artifacts import (
    ListDocumentArtifactsUseCase,
)
from app.modules.document.application.use_cases.list_documents import (
    ListDocumentsUseCase,
)


NOW = datetime(2026, 8, 2, 12, 0, 0)


def _document(document_id: int = 7):
    return SimpleNamespace(
        id=document_id,
        doc_code=f"DOC_{document_id}",
        kb_id=3,
        domain_code="policy",
        business_scene=None,
        title="测试文档",
        original_filename="test.txt",
        file_size=128,
        source_type="txt",
        source_uri=f"storage/raw/local/DOC_{document_id}.txt",
        cleaned_uri=f"storage/cleaned/DOC_{document_id}.cleaned.txt",
        content_hash="a" * 64,
        active_content_hash="a" * 64,
        lifecycle_status="active",
        storage_status="active",
        version=1,
        status="chunked",
        replaced_by=None,
        risk_level="low",
        effective_at=None,
        expired_at=None,
        created_by_actor_code="actor",
        created_at=NOW,
        updated_at=NOW,
        indexed_at=None,
    )


class _Documents:
    def __init__(self, documents):
        self.documents = documents
        self.list_kwargs = None
        self.count_kwargs = None

    def get_by_id(self, document_id):
        return next(
            (item for item in self.documents if item.id == document_id),
            None,
        )

    def list_filtered(self, **kwargs):
        self.list_kwargs = kwargs
        return self.documents

    def count_filtered(self, **kwargs):
        self.count_kwargs = kwargs
        return len(self.documents)


class _Artifacts:
    def __init__(self, items):
        self.items = items

    def list_by_document_id(self, document_id):
        return [item for item in self.items if item.document_id == document_id]


class _ParentBlocks:
    def count_active_by_doc_id(self, document_id):
        return 2


class _ChildChunks:
    def count_by_vector_status_for_document(self, document_id):
        return {"pending": 1, "indexed": 3}


class _Uow:
    def __init__(self, documents, artifacts=None):
        self.documents = documents
        self.document_artifacts = _Artifacts(artifacts or [])
        self.parent_blocks = _ParentBlocks()
        self.child_chunks = _ChildChunks()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class DocumentQueryUseCasesTest(unittest.TestCase):
    def test_get_document_returns_complete_application_dto(self) -> None:
        documents = _Documents([_document()])
        use_case = GetDocumentUseCase(
            uow_factory=lambda: _Uow(documents)
        )

        result = use_case.execute(7)

        self.assertEqual(result.id, 7)
        self.assertEqual(result.status, "chunked")
        self.assertEqual(result.cleaned_uri, "storage/cleaned/DOC_7.cleaned.txt")

    def test_get_document_rejects_missing_document(self) -> None:
        use_case = GetDocumentUseCase(
            uow_factory=lambda: _Uow(_Documents([]))
        )

        with self.assertRaises(DocumentApplicationError) as raised:
            use_case.execute(404)

        self.assertEqual(raised.exception.status_code, 404)

    def test_list_documents_maps_filters_and_pagination(self) -> None:
        documents = _Documents([_document(9)])
        use_case = ListDocumentsUseCase(
            uow_factory=lambda: _Uow(documents)
        )
        query = DocumentListQuery(
            kb_id=3,
            status="chunked",
            source_type="txt",
            lifecycle_status="active",
            limit=20,
            offset=5,
        )

        result = use_case.execute(query)

        expected = {
            "kb_id": 3,
            "status": "chunked",
            "source_type": "txt",
            "lifecycle_status": "active",
        }
        self.assertEqual(
            documents.list_kwargs,
            {**expected, "limit": 20, "offset": 5},
        )
        self.assertEqual(documents.count_kwargs, expected)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].id, 9)

    def test_pipeline_state_aggregates_parent_and_vector_counts(self) -> None:
        documents = _Documents([_document()])
        use_case = GetDocumentPipelineStateUseCase(
            uow_factory=lambda: _Uow(documents)
        )

        result = use_case.execute(7)

        self.assertEqual(result.parent_count, 2)
        self.assertEqual(result.child_count, 4)
        self.assertEqual(
            result.vector_status_counts,
            {"pending": 1, "indexed": 3},
        )

    def test_list_artifacts_maps_metadata_without_exposing_orm(self) -> None:
        artifact = SimpleNamespace(
            id=11,
            document_id=7,
            artifact_code="ART_11",
            artifact_type="cleaned_text",
            artifact_role="process_output",
            artifact_format="txt",
            artifact_uri="storage/cleaned/DOC_7.cleaned.txt",
            artifact_hash="b" * 64,
            hash_algorithm="sha256",
            provider=None,
            processor="TextProcessor",
            file_size=100,
            char_count=90,
            line_count=5,
            status="active",
            metadata_json={"warnings": []},
            created_at=NOW,
            updated_at=NOW,
        )
        documents = _Documents([_document()])
        use_case = ListDocumentArtifactsUseCase(
            uow_factory=lambda: _Uow(documents, [artifact])
        )

        result = use_case.execute(7)

        self.assertEqual(result.document_id, 7)
        self.assertEqual(result.source_uri, "storage/raw/local/DOC_7.txt")
        self.assertEqual(result.items[0].artifact_code, "ART_11")
        self.assertEqual(result.items[0].metadata, {"warnings": []})


if __name__ == "__main__":
    unittest.main()
