"""文档向量索引领取、事务外执行、完成与补偿的短事务测试。"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_status import DocumentStatus
from app.constants.document_storage_status import DocumentStorageStatus


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT_DIR / "app" / "services" / "vector_indexing_service.py"


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _KeywordModel(SimpleNamespace):
    def __init__(self, **values) -> None:
        super().__init__(**values)


class _PointStruct:
    def __init__(self, *, id: int, vector: list[float], payload: dict) -> None:
        self.id = id
        self.vector = vector
        self.payload = payload


def _load_service_module():
    replacements = {
        "fastapi": types.ModuleType("fastapi"),
        "qdrant_client": types.ModuleType("qdrant_client"),
        "qdrant_client.models": types.ModuleType("qdrant_client.models"),
        "app.app_config.settings": types.ModuleType("app.app_config.settings"),
        "app.db.uow": types.ModuleType("app.db.uow"),
        "app.schemas.vector_indexing": types.ModuleType(
            "app.schemas.vector_indexing"
        ),
        "app.services.embedding_service": types.ModuleType(
            "app.services.embedding_service"
        ),
        "app.vectorstores.qdrant_store": types.ModuleType(
            "app.vectorstores.qdrant_store"
        ),
    }
    replacements["fastapi"].HTTPException = _HTTPException
    replacements["qdrant_client.models"].PointStruct = _PointStruct
    replacements["app.app_config.settings"].EMBEDDING_BATCH_SIZE = 2
    replacements["app.app_config.settings"].EMBEDDING_VECTOR_SIZE = 3
    replacements["app.db.uow"].SQLAlchemyUnitOfWork = object
    replacements["app.schemas.vector_indexing"].VectorIndexingResponse = (
        _KeywordModel
    )
    replacements["app.services.embedding_service"].EmbeddingService = object
    replacements["app.vectorstores.qdrant_store"].QdrantVectorStore = object

    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "vector_indexing_service_under_test",
            SERVICE_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的向量索引 Service")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("vector_indexing_service_under_test", None)
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


class _ChildChunkRepository:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.chunks = chunks
        self.list_indexable_calls: list[tuple[int, set[str]]] = []
        self.lock_calls: list[tuple[int, tuple[int, ...]]] = []
        self.mark_indexing_calls: list[list[int]] = []
        self.mark_indexed_calls: list[list[int]] = []
        self.mark_failed_calls: list[list[int]] = []

    def list_indexable_by_doc_id(self, document_id: int, statuses: set[str]):
        self.list_indexable_calls.append((document_id, statuses))
        return sorted(
            [
                chunk
                for chunk in self.chunks
                if chunk.doc_id == document_id
                and chunk.status == "active"
                and chunk.vector_status in statuses
            ],
            key=lambda chunk: (chunk.parent_id, chunk.chunk_index),
        )

    def list_by_ids_for_update(self, document_id: int, chunk_ids):
        ordered_ids = tuple(sorted(set(chunk_ids)))
        self.lock_calls.append((document_id, ordered_ids))
        return sorted(
            [
                chunk
                for chunk in self.chunks
                if chunk.doc_id == document_id and chunk.id in ordered_ids
            ],
            key=lambda chunk: chunk.id,
        )

    def mark_indexing(self, chunks) -> None:
        self.mark_indexing_calls.append([chunk.id for chunk in chunks])
        for chunk in chunks:
            chunk.vector_status = "indexing"

    def mark_indexed_many(self, chunks) -> None:
        self.mark_indexed_calls.append([chunk.id for chunk in chunks])
        for chunk in chunks:
            chunk.vector_status = "indexed"
            chunk.qdrant_point_id = str(chunk.id)
            chunk.indexed_at = "now"

    def mark_failed(self, chunks) -> None:
        self.mark_failed_calls.append([chunk.id for chunk in chunks])
        for chunk in chunks:
            if chunk.vector_status == "indexing":
                chunk.vector_status = "failed"


class _UnitOfWork:
    def __init__(
        self,
        documents: dict[int, SimpleNamespace],
        chunks: list[SimpleNamespace],
    ) -> None:
        self.documents = _DocumentRepository(documents)
        self.child_chunks = _ChildChunkRepository(chunks)
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
        chunks: list[SimpleNamespace],
    ) -> None:
        self.documents = documents
        self.chunks = chunks
        self.instances: list[_UnitOfWork] = []

    def __call__(self) -> _UnitOfWork:
        uow = _UnitOfWork(self.documents, self.chunks)
        self.instances.append(uow)
        return uow


class _EmbeddingClient:
    def __init__(self, factory: _UnitOfWorkFactory, responder=None) -> None:
        self.factory = factory
        self.responder = responder
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if any(uow.active for uow in self.factory.instances):
            raise AssertionError("Embedding 调用发生在数据库事务内")
        self.calls.append(texts)
        if self.responder is not None:
            return self.responder(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class _VectorStore:
    def __init__(
        self,
        factory: _UnitOfWorkFactory,
        *,
        fail_upsert: bool = False,
        on_upsert=None,
    ) -> None:
        self.factory = factory
        self.fail_upsert = fail_upsert
        self.on_upsert = on_upsert
        self.upsert_calls: list[list[_PointStruct]] = []
        self.delete_calls: list[list[int]] = []

    def upsert_points(self, points: list[_PointStruct]) -> None:
        if any(uow.active for uow in self.factory.instances):
            raise AssertionError("Qdrant upsert 发生在数据库事务内")
        self.upsert_calls.append(points)
        if self.on_upsert is not None:
            self.on_upsert(points)
        if self.fail_upsert:
            raise RuntimeError("Qdrant failed")

    def delete_points(self, point_ids: list[int]) -> None:
        if any(uow.active for uow in self.factory.instances):
            raise AssertionError("Qdrant delete 发生在数据库事务内")
        self.delete_calls.append(point_ids)


def _document(
    *,
    status: str = DocumentStatus.CHUNKED.value,
    lifecycle_status: str = DocumentLifecycleStatus.ACTIVE.value,
    storage_status: str = DocumentStorageStatus.ACTIVE.value,
    active_content_hash: str | None = "active-hash",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        source_type="md",
        title="Document title",
        original_filename="document.md",
        status=status,
        lifecycle_status=lifecycle_status,
        storage_status=storage_status,
        active_content_hash=active_content_hash,
        indexed_at=None,
    )


def _chunk(
    chunk_id: int,
    *,
    vector_status: str = "pending",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=chunk_id,
        chunk_code=f"CK_{chunk_id}",
        embedding_text=f"embedding {chunk_id}",
        parent_id=100 + chunk_id,
        doc_id=1,
        kb_id=10,
        domain_code="domain",
        business_scene="scene",
        chunk_index=chunk_id - 1,
        section_path=["Section"],
        source_row_index=None,
        status="active",
        vector_status=vector_status,
        qdrant_point_id=None,
        indexed_at=None,
    )


class VectorIndexingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = _load_service_module()

    def setUp(self) -> None:
        self.original_uow = self.service.SQLAlchemyUnitOfWork

    def tearDown(self) -> None:
        self.service.SQLAlchemyUnitOfWork = self.original_uow

    def _use(
        self,
        document: SimpleNamespace,
        chunks: list[SimpleNamespace],
    ) -> _UnitOfWorkFactory:
        factory = _UnitOfWorkFactory({document.id: document}, chunks)
        self.service.SQLAlchemyUnitOfWork = factory
        return factory

    def test_chunked_claim_sets_document_and_indexable_chunks_indexing(self) -> None:
        document = _document()
        chunks = [
            _chunk(1, vector_status="pending"),
            _chunk(2, vector_status="failed"),
            _chunk(3, vector_status="indexed"),
        ]
        factory = self._use(document, chunks)

        context = self.service._claim_indexing(document.id)

        self.assertEqual(document.status, DocumentStatus.INDEXING.value)
        self.assertEqual([chunk.chunk_id for chunk in context.chunks], [1, 2])
        self.assertEqual(chunks[0].vector_status, "indexing")
        self.assertEqual(chunks[1].vector_status, "indexing")
        self.assertEqual(chunks[2].vector_status, "indexed")
        self.assertEqual(factory.instances[0].commit_count, 1)

    def test_failed_claim_requires_pending_or_failed_chunk(self) -> None:
        document = _document(status=DocumentStatus.FAILED.value)
        indexed_chunk = _chunk(1, vector_status="indexed")
        factory = self._use(document, [indexed_chunk])

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service._claim_indexing(document.id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(factory.instances[0].commit_count, 0)

        retry_chunk = _chunk(2, vector_status="failed")
        factory = self._use(document, [indexed_chunk, retry_chunk])
        context = self.service._claim_indexing(document.id)

        self.assertEqual([chunk.chunk_id for chunk in context.chunks], [2])
        self.assertEqual(retry_chunk.vector_status, "indexing")
        self.assertEqual(indexed_chunk.vector_status, "indexed")
        self.assertEqual(factory.instances[0].commit_count, 1)

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
                chunk = _chunk(1)
                factory = self._use(document, [chunk])

                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service._claim_indexing(document.id)

                self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(document.status, DocumentStatus.CHUNKED.value)
                self.assertEqual(chunk.vector_status, "pending")
                self.assertEqual(factory.instances[0].commit_count, 0)

    def test_success_batches_outside_transactions_and_marks_indexed(self) -> None:
        document = _document()
        chunks = [_chunk(1), _chunk(2), _chunk(3)]
        factory = self._use(document, chunks)
        embedding = _EmbeddingClient(factory)
        vector_store = _VectorStore(factory)

        response = self.service.index_document_vectors(
            document.id,
            embedding_client=embedding,
            vector_store=vector_store,
        )

        self.assertEqual(
            embedding.calls,
            [["embedding 1", "embedding 2"], ["embedding 3"]],
        )
        self.assertEqual(len(vector_store.upsert_calls), 2)
        points = [point for batch in vector_store.upsert_calls for point in batch]
        self.assertEqual([point.id for point in points], [1, 2, 3])
        self.assertEqual(
            points[0].payload,
            {
                "document_id": 1,
                "kb_id": 10,
                "parent_block_id": 101,
                "child_chunk_id": 1,
                "chunk_index": 0,
                "chunk_code": "CK_1",
                "section_path": ["Section"],
                "source_row_index": None,
                "domain_code": "domain",
                "business_scene": "scene",
                "source_type": "md",
                "title": "Document title",
                "original_filename": "document.md",
            },
        )
        self.assertEqual(document.status, DocumentStatus.INDEXED.value)
        self.assertIsNotNone(document.indexed_at)
        self.assertTrue(all(chunk.vector_status == "indexed" for chunk in chunks))
        self.assertEqual([chunk.qdrant_point_id for chunk in chunks], ["1", "2", "3"])
        self.assertEqual(response.total_chunks, 3)
        self.assertEqual(response.indexed_chunks, 3)
        self.assertEqual(len(factory.instances), 2)
        self.assertEqual(factory.instances[0].commit_count, 1)
        self.assertEqual(factory.instances[1].commit_count, 1)

    def test_embedding_count_mismatch_marks_document_and_chunks_failed(self) -> None:
        document = _document(active_content_hash="keep-me")
        chunks = [_chunk(1), _chunk(2)]
        factory = self._use(document, chunks)
        embedding = _EmbeddingClient(factory, responder=lambda texts: [[0.1] * 3])
        vector_store = _VectorStore(factory)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.index_document_vectors(
                document.id,
                embedding_client=embedding,
                vector_store=vector_store,
            )

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertTrue(all(chunk.vector_status == "failed" for chunk in chunks))
        self.assertEqual(document.active_content_hash, "keep-me")
        self.assertEqual(vector_store.upsert_calls, [])
        self.assertEqual(vector_store.delete_calls, [])

    def test_embedding_dimension_mismatch_marks_failed(self) -> None:
        document = _document()
        chunks = [_chunk(1)]
        factory = self._use(document, chunks)
        embedding = _EmbeddingClient(factory, responder=lambda texts: [[0.1, 0.2]])
        vector_store = _VectorStore(factory)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.index_document_vectors(
                document.id,
                embedding_client=embedding,
                vector_store=vector_store,
            )

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(chunks[0].vector_status, "failed")
        self.assertEqual(vector_store.upsert_calls, [])

    def test_qdrant_failure_marks_failed_and_deletes_attempted_points(self) -> None:
        document = _document(active_content_hash="keep-me")
        chunks = [_chunk(1), _chunk(2)]
        factory = self._use(document, chunks)
        embedding = _EmbeddingClient(factory)
        vector_store = _VectorStore(factory, fail_upsert=True)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.index_document_vectors(
                document.id,
                embedding_client=embedding,
                vector_store=vector_store,
            )

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertTrue(all(chunk.vector_status == "failed" for chunk in chunks))
        self.assertEqual(document.active_content_hash, "keep-me")
        self.assertEqual(vector_store.delete_calls, [[1, 2]])

    def test_deletion_during_execution_aborts_and_deletes_points(self) -> None:
        document = _document()
        chunks = [_chunk(1), _chunk(2)]
        factory = self._use(document, chunks)
        embedding = _EmbeddingClient(factory)

        def deactivate(points) -> None:
            document.lifecycle_status = DocumentLifecycleStatus.DELETED.value
            document.storage_status = DocumentStorageStatus.ARCHIVING.value
            document.active_content_hash = None

        vector_store = _VectorStore(factory, on_upsert=deactivate)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.index_document_vectors(
                document.id,
                embedding_client=embedding,
                vector_store=vector_store,
            )

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
        self.assertTrue(all(chunk.vector_status == "failed" for chunk in chunks))
        self.assertEqual(vector_store.delete_calls, [[1, 2]])
        self.assertEqual(len(factory.instances), 3)
        self.assertEqual(factory.instances[1].commit_count, 0)
        self.assertEqual(factory.instances[2].commit_count, 1)

    def test_chunk_status_change_aborts_completion_and_compensates(self) -> None:
        document = _document()
        chunks = [_chunk(1), _chunk(2)]
        factory = self._use(document, chunks)
        embedding = _EmbeddingClient(factory)

        def change_chunk(points) -> None:
            chunks[0].vector_status = "failed"

        vector_store = _VectorStore(factory, on_upsert=change_chunk)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.index_document_vectors(
                document.id,
                embedding_client=embedding,
                vector_store=vector_store,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(document.status, DocumentStatus.FAILED.value)
        self.assertEqual(vector_store.delete_calls, [[1, 2]])
        self.assertTrue(all(chunk.vector_status == "failed" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
