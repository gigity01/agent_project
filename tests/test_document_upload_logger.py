"""文档上传拒绝与前置异常的事实语义测试。"""

import unittest
from types import SimpleNamespace

from core.observability.document_upload_logger import DocumentUploadLogger


class _MemoryWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class DocumentUploadLoggerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.upload_logger = DocumentUploadLogger()
        self.upload_logger.writer = _MemoryWriter()

    def test_validation_rejection_does_not_invent_document_status(self) -> None:
        self.upload_logger.failed_by_http_exception(
            exc=_HTTPException(400, "必须上传文件"),
            phase="validate",
            doc_code="DOC_001",
            kb_id=1,
            domain_code="domain",
            business_scene="scene",
            title="title",
            filename=None,
            source_type=None,
            source_uri=None,
            file_size=0,
            cleanup_success=True,
        )

        event = self.upload_logger.writer.events[0]
        self.assertEqual(event["phase"], "validate")
        self.assertEqual(event["outcome"], "rejected")
        self.assertFalse(event["document_created"])
        self.assertIsNone(event["status_after"])
        self.assertIsNone(event["filename"])
        self.assertIsNone(event["source_type"])
        self.assertIsNone(event["source_uri"])

    def test_storage_preparation_error_has_no_document_status(self) -> None:
        self.upload_logger.failed_by_unexpected_exception(
            exc=OSError("read only"),
            phase="prepare_storage",
            doc_code="DOC_001",
            kb_id=1,
            domain_code="domain",
            business_scene="scene",
            title="title",
            filename="document.txt",
            source_type="txt",
            source_uri=None,
            file_size=0,
            cleanup_success=True,
        )

        event = self.upload_logger.writer.events[0]
        self.assertEqual(event["phase"], "prepare_storage")
        self.assertEqual(event["outcome"], "error")
        self.assertFalse(event["document_created"])
        self.assertIsNone(event["status_after"])

    def test_duplicate_detected_uses_finalize_phase(self) -> None:
        self.upload_logger.duplicate_detected(
            doc_code="DOC_002",
            kb_id=1,
            content_hash="hash",
            duplicated_document=SimpleNamespace(
                id=13,
                doc_code="DOC_001",
            ),
        )

        event = self.upload_logger.writer.events[0]
        self.assertEqual(event["phase"], "finalize")


if __name__ == "__main__":
    unittest.main()
