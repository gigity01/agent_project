"""Document Router 从应用容器取得用例的测试。"""

from __future__ import annotations

import unittest
from unittest import mock

import httpx
from fastapi import FastAPI

from app.modules.document.presentation.dependencies import (
    get_process_document_use_case,
)
from app.modules.document.presentation.router import router


class DocumentUseCaseInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_process_endpoint_uses_injected_use_case(self) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api")
        use_case = mock.Mock()
        use_case.execute.return_value = {
            "document_id": 42,
            "doc_code": "DOC_42",
            "source_type": "txt",
            "source_uri": "storage/raw/local/DOC_42.txt",
            "cleaned_uri": "storage/cleaned/DOC_42.cleaned.txt",
            "status": "processed",
        }

        async def get_use_case():
            return use_case

        app.dependency_overrides[get_process_document_use_case] = get_use_case
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/admin/documents/42/process"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document_id"], 42)
        use_case.execute.assert_called_once_with(42)


if __name__ == "__main__":
    unittest.main()
