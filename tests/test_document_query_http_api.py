"""Document 查询 HTTP API 与 Application Use Case 复用测试。"""

from __future__ import annotations

import unittest
from unittest import mock

import httpx
from fastapi import FastAPI

from app.modules.document.presentation.dependencies import (
    get_document_chunk_statistics_use_case,
    get_document_pipeline_state_use_case,
    get_document_use_case,
    get_knowledge_base_statistics_use_case,
    get_list_child_chunks_use_case,
    get_list_document_artifacts_use_case,
    get_list_parent_blocks_use_case,
    get_search_document_artifacts_use_case,
    get_search_documents_use_case,
)
from app.modules.document.presentation.router import (
    artifact_router,
    child_chunk_router,
    knowledge_base_router,
    parent_block_router,
    router,
)


NOW = "2026-08-03T12:00:00"


def _document() -> dict:
    return {
        "id": 7,
        "doc_code": "DOC_7",
        "kb_id": 3,
        "domain_code": "policy",
        "business_scene": None,
        "title": "测试文档",
        "original_filename": "test.md",
        "file_size": 128,
        "source_type": "md",
        "source_uri": "storage/raw/local/7.md",
        "cleaned_uri": "storage/cleaned/7.md",
        "content_hash": "a" * 64,
        "active_content_hash": "a" * 64,
        "lifecycle_status": "active",
        "storage_status": "active",
        "version": 1,
        "status": "indexed",
        "replaced_by": None,
        "risk_level": "low",
        "effective_at": None,
        "expired_at": None,
        "created_by_actor_code": "actor",
        "created_at": NOW,
        "updated_at": NOW,
        "indexed_at": NOW,
    }


def _service(result: dict) -> mock.Mock:
    service = mock.Mock()
    service.execute.return_value = result
    return service


class DocumentQueryHttpApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.app = FastAPI()
        for query_router in (
            router,
            artifact_router,
            parent_block_router,
            child_chunk_router,
            knowledge_base_router,
        ):
            self.app.include_router(query_router, prefix="/api")

        self.services = {
            get_document_use_case: _service(_document()),
            get_search_documents_use_case: _service(
                {
                    "items": [_document()],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                }
            ),
            get_document_pipeline_state_use_case: _service(
                {
                    "document_id": 7,
                    "doc_code": "DOC_7",
                    "source_type": "md",
                    "source_uri": "storage/raw/local/7.md",
                    "cleaned_uri": "storage/cleaned/7.md",
                    "document_status": "indexed",
                    "lifecycle_status": "active",
                    "storage_status": "active",
                    "parent_count": 1,
                    "child_count": 2,
                    "vector_status_counts": {"indexed": 2},
                    "indexed_at": NOW,
                }
            ),
            get_list_document_artifacts_use_case: _service(
                {
                    "document_id": 7,
                    "source_uri": "storage/raw/local/7.md",
                    "source_type": "md",
                    "original_filename": "test.md",
                    "items": [],
                }
            ),
            get_search_document_artifacts_use_case: _service(
                {"items": [], "total": 0, "limit": 20, "offset": 0}
            ),
            get_list_parent_blocks_use_case: _service(
                {"items": [], "total": 0, "limit": 20, "offset": 0}
            ),
            get_list_child_chunks_use_case: _service(
                {"items": [], "total": 0, "limit": 20, "offset": 0}
            ),
            get_document_chunk_statistics_use_case: _service(
                {
                    "document_id": 7,
                    "doc_code": "DOC_7",
                    "parent_count": 1,
                    "child_count": 2,
                    "parent_status_counts": {"active": 1},
                    "child_status_counts": {"active": 2},
                    "vector_status_counts": {"indexed": 2},
                    "chunk_type_counts": {"text": 2},
                    "chunks_with_vector_id": 2,
                    "chunks_without_vector_id": 0,
                }
            ),
            get_knowledge_base_statistics_use_case: _service(
                {
                    "kb_id": 3,
                    "kb_code": "KB_3",
                    "name": "政策库",
                    "domain_code": "policy",
                    "business_scene": None,
                    "status": "active",
                    "visibility": "external",
                    "document_count": 1,
                    "active_document_count": 1,
                    "failed_document_count": 0,
                    "indexed_document_count": 1,
                    "parent_count": 1,
                    "child_count": 2,
                    "vector_status_counts": {"indexed": 2},
                }
            ),
        }
        for dependency, service in self.services.items():
            def override(service=service):
                def get_service():
                    return service

                return get_service

            self.app.dependency_overrides[dependency] = override()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_all_query_routes_delegate_to_shared_use_cases(self) -> None:
        requests = (
            ("GET", "/api/admin/documents/7", None, 200),
            (
                "POST",
                "/api/admin/documents/search",
                {"kb_ids": [3], "statuses": ["indexed"], "limit": 20},
                200,
            ),
            (
                "GET",
                "/api/admin/documents/7/pipeline-state",
                None,
                200,
            ),
            ("GET", "/api/admin/documents/7/artifacts", None, 200),
            (
                "POST",
                "/api/admin/document-artifacts/search",
                {"document_ids": [7], "limit": 20},
                200,
            ),
            (
                "POST",
                "/api/admin/parent-blocks/search",
                {"document_ids": [7], "limit": 20},
                200,
            ),
            (
                "POST",
                "/api/admin/child-chunks/search",
                {"document_id": 7, "limit": 20},
                200,
            ),
            (
                "GET",
                "/api/admin/documents/7/chunk-statistics",
                None,
                200,
            ),
            (
                "GET",
                "/api/admin/knowledge-bases/3/statistics",
                None,
                200,
            ),
        )
        for method, path, payload, expected_status in requests:
            with self.subTest(path=path):
                response = await self.client.request(
                    method,
                    path,
                    json=payload,
                )
                self.assertEqual(response.status_code, expected_status)

        self.services[get_document_use_case].execute.assert_called_once_with(7)
        search_query = self.services[
            get_search_documents_use_case
        ].execute.call_args.args[0]
        self.assertEqual(search_query.kb_ids, [3])
        self.assertEqual(search_query.statuses, ["indexed"])

    async def test_search_rejects_arbitrary_sort_field(self) -> None:
        response = await self.client.post(
            "/api/admin/documents/search",
            json={"sort_by": "content_hash"},
        )

        self.assertEqual(response.status_code, 422)
        self.services[
            get_search_documents_use_case
        ].execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
